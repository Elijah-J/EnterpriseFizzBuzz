"""
Enterprise FizzBuzz Platform - FizzTPM Trusted Platform Module 2.0 Test Suite

Comprehensive tests for the TPM 2.0 simulator, covering PCR bank extend
and read operations, measurement event logging, sealed storage with
PCR binding, unseal with PCR mismatch detection, NVRAM define/write/read/lock,
remote attestation quote generation, random number generation, middleware
pipeline integration, dashboard rendering, and exception handling.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizztpm import (
    FIZZTPM_VERSION,
    MIDDLEWARE_PRIORITY,
    NUM_PCRS,
    PCR_SIZE_BYTES,
    NVRAMStorage,
    PCRAlgorithm,
    PCRBank,
    SealedStorage,
    TPMDashboard,
    TPMDevice,
    TPMMiddleware,
    create_fizztpm_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    TPMAttestationError,
    TPMAuthorizationError,
    TPMNVRAMError,
    TPMPCRError,
    TPMRandomError,
    TPMSealError,
    TPMUnsealError,
)


# =========================================================================
# Constants
# =========================================================================

class TestConstants:
    def test_version(self):
        assert FIZZTPM_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 242

    def test_num_pcrs(self):
        assert NUM_PCRS == 24

    def test_pcr_size(self):
        assert PCR_SIZE_BYTES == 32


# =========================================================================
# PCR Bank
# =========================================================================

class TestPCRBank:
    def test_initial_pcr_is_zero(self):
        bank = PCRBank()
        val = bank.read(0)
        assert val == b"\x00" * PCR_SIZE_BYTES

    def test_extend_changes_value(self):
        bank = PCRBank()
        initial = bank.read(0)
        new_val = bank.extend(0, b"measurement")
        assert new_val != initial
        assert len(new_val) == PCR_SIZE_BYTES

    def test_extend_is_deterministic(self):
        bank1 = PCRBank()
        bank2 = PCRBank()
        val1 = bank1.extend(0, b"same_data")
        val2 = bank2.extend(0, b"same_data")
        assert val1 == val2

    def test_extend_is_order_dependent(self):
        bank1 = PCRBank()
        bank1.extend(0, b"A")
        val1 = bank1.extend(0, b"B")
        bank2 = PCRBank()
        bank2.extend(0, b"B")
        val2 = bank2.extend(0, b"A")
        assert val1 != val2

    def test_read_out_of_range_raises(self):
        bank = PCRBank()
        with pytest.raises(TPMPCRError):
            bank.read(24)

    def test_extend_out_of_range_raises(self):
        bank = PCRBank()
        with pytest.raises(TPMPCRError):
            bank.extend(-1, b"data")

    def test_reset_resettable_pcr(self):
        bank = PCRBank()
        bank.extend(17, b"data")
        bank.reset(17)
        assert bank.read(17) == b"\x00" * PCR_SIZE_BYTES

    def test_reset_static_pcr_raises(self):
        bank = PCRBank()
        with pytest.raises(TPMPCRError):
            bank.reset(0)

    def test_event_log(self):
        bank = PCRBank()
        bank.extend(0, b"event1")
        bank.extend(0, b"event2")
        log = bank.get_event_log()
        assert len(log) == 2
        assert log[0].data == b"event1"

    def test_extend_count(self):
        bank = PCRBank()
        bank.extend(5, b"a")
        bank.extend(5, b"b")
        assert bank.get_extend_count(5) == 2


# =========================================================================
# Sealed Storage
# =========================================================================

class TestSealedStorage:
    def test_seal_and_unseal(self):
        bank = PCRBank()
        storage = SealedStorage(bank)
        handle = storage.seal(b"secret_data", pcr_index=0)
        data = storage.unseal(handle)
        assert data == b"secret_data"

    def test_unseal_fails_after_pcr_change(self):
        bank = PCRBank()
        storage = SealedStorage(bank)
        handle = storage.seal(b"secret", pcr_index=0)
        bank.extend(0, b"measurement")
        with pytest.raises(TPMUnsealError):
            storage.unseal(handle)

    def test_seal_empty_data_raises(self):
        bank = PCRBank()
        storage = SealedStorage(bank)
        with pytest.raises(TPMSealError):
            storage.seal(b"", pcr_index=0)

    def test_unseal_wrong_auth_raises(self):
        bank = PCRBank()
        storage = SealedStorage(bank)
        handle = storage.seal(b"data", pcr_index=0, auth=b"correct")
        with pytest.raises(TPMAuthorizationError):
            storage.unseal(handle, auth=b"wrong")

    def test_blob_count(self):
        bank = PCRBank()
        storage = SealedStorage(bank)
        storage.seal(b"a", pcr_index=0)
        storage.seal(b"b", pcr_index=1)
        assert storage.blob_count == 2


# =========================================================================
# NVRAM
# =========================================================================

class TestNVRAM:
    def test_define_and_write_read(self):
        nv = NVRAMStorage()
        nv.define(0x01000001, 64)
        nv.write(0x01000001, b"hello")
        assert nv.read(0x01000001) == b"hello"

    def test_read_undefined_raises(self):
        nv = NVRAMStorage()
        with pytest.raises(TPMNVRAMError):
            nv.read(0xDEAD)

    def test_write_undefined_raises(self):
        nv = NVRAMStorage()
        with pytest.raises(TPMNVRAMError):
            nv.write(0xDEAD, b"data")

    def test_define_duplicate_raises(self):
        nv = NVRAMStorage()
        nv.define(0x01, 32)
        with pytest.raises(TPMNVRAMError):
            nv.define(0x01, 32)

    def test_lock_prevents_write(self):
        nv = NVRAMStorage()
        nv.define(0x01, 64)
        nv.write(0x01, b"initial")
        nv.lock(0x01)
        with pytest.raises(TPMNVRAMError):
            nv.write(0x01, b"updated")

    def test_write_too_large_raises(self):
        nv = NVRAMStorage()
        nv.define(0x01, 4)
        with pytest.raises(TPMNVRAMError):
            nv.write(0x01, b"toolong!")


# =========================================================================
# TPMDevice
# =========================================================================

class TestTPMDevice:
    def test_pcr_extend_and_read(self):
        dev = TPMDevice()
        dev.pcr_extend(0, b"boot")
        val = dev.pcr_read(0)
        assert val != b"\x00" * PCR_SIZE_BYTES

    def test_quote(self):
        dev = TPMDevice()
        dev.pcr_extend(0, b"data")
        quote = dev.quote([0], nonce=b"challenge")
        assert "pcr_values" in quote
        assert "pcr_digest" in quote
        assert quote["nonce"] == b"challenge".hex()

    def test_quote_empty_pcrs_raises(self):
        dev = TPMDevice()
        with pytest.raises(TPMAttestationError):
            dev.quote([], nonce=b"nonce")

    def test_quote_no_nonce_raises(self):
        dev = TPMDevice()
        with pytest.raises(TPMAttestationError):
            dev.quote([0], nonce=b"")

    def test_get_random(self):
        dev = TPMDevice()
        data = dev.get_random(32)
        assert len(data) == 32

    def test_get_random_invalid_raises(self):
        dev = TPMDevice()
        with pytest.raises(TPMRandomError):
            dev.get_random(0)

    def test_get_stats(self):
        dev = TPMDevice()
        dev.pcr_extend(0, b"x")
        stats = dev.get_stats()
        assert stats["total_extends"] == 1
        assert stats["commands_executed"] == 1


# =========================================================================
# Middleware
# =========================================================================

class TestMiddleware:
    def _make_context(self, number: int):
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        return ProcessingContext(number=number, session_id="test-tpm")

    def test_middleware_name(self):
        _, mw = create_fizztpm_subsystem()
        assert mw.get_name() == "fizztpm"

    def test_middleware_priority(self):
        _, mw = create_fizztpm_subsystem()
        assert mw.get_priority() == 242

    def test_classifies_and_extends_pcr(self):
        dev, mw = create_fizztpm_subsystem()
        ctx = self._make_context(15)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["tpm_classification"] == "FizzBuzz"
        assert result.metadata["tpm_enabled"] is True
        # PCR should no longer be zero
        pcr_val = dev.pcr_read(17)
        assert pcr_val != b"\x00" * PCR_SIZE_BYTES

    def test_multiple_extends_chain(self):
        dev, mw = create_fizztpm_subsystem()
        ctx1 = self._make_context(3)
        mw.process(ctx1, lambda c: c)
        val1 = dev.pcr_read(17)
        ctx2 = self._make_context(5)
        mw.process(ctx2, lambda c: c)
        val2 = dev.pcr_read(17)
        assert val1 != val2  # Each extend changes the PCR


# =========================================================================
# Dashboard
# =========================================================================

class TestDashboard:
    def test_dashboard_renders(self):
        dev, _ = create_fizztpm_subsystem()
        dev.pcr_extend(0, b"boot")
        output = TPMDashboard.render(dev)
        assert "FizzTPM" in output
        assert "sha256" in output


# =========================================================================
# Factory
# =========================================================================

class TestFactory:
    def test_create_subsystem(self):
        dev, mw = create_fizztpm_subsystem()
        assert isinstance(dev, TPMDevice)
        assert isinstance(mw, TPMMiddleware)

    def test_create_subsystem_sha384(self):
        dev, _ = create_fizztpm_subsystem(algorithm=PCRAlgorithm.SHA384)
        assert dev._algorithm == PCRAlgorithm.SHA384

"""
Enterprise FizzBuzz Platform - FizzSGX Intel SGX Enclave Simulator Test Suite

Comprehensive tests for the SGX enclave simulator, covering enclave
creation and lifecycle, ECALL/OCALL bridge, sealed storage, remote
attestation, memory encryption engine, middleware pipeline integration,
dashboard rendering, and exception handling.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzsgx import (
    FIZZSGX_VERSION,
    MIDDLEWARE_PRIORITY,
    MAX_ENCLAVES,
    AttestationEngine,
    Enclave,
    EnclaveState,
    MemoryEncryptionEngine,
    SGXDashboard,
    SGXMiddleware,
    SGXPlatform,
    SGXSealedStorage,
    SealPolicy,
    create_fizzsgx_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    SGXAttestationError,
    SGXECallError,
    SGXEnclaveCreationError,
    SGXMemoryError,
    SGXMeasurementError,
    SGXOCallError,
    SGXSealError,
)


# =========================================================================
# Helpers
# =========================================================================

@dataclass
class ProcessingContext:
    number: int
    session_id: str = "test-session"
    results: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


def _make_enclave(eid: str = "test-enclave") -> Enclave:
    enc = Enclave(eid)
    enc.initialize()
    enc.run()
    return enc


# =========================================================================
# Constants
# =========================================================================

class TestConstants:
    def test_version(self):
        assert FIZZSGX_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 249

    def test_max_enclaves(self):
        assert MAX_ENCLAVES == 8


# =========================================================================
# Enclave Lifecycle
# =========================================================================

class TestEnclave:
    def test_create(self):
        enc = Enclave("test")
        assert enc.state == EnclaveState.CREATED

    def test_initialize(self):
        enc = Enclave("test")
        enc.initialize()
        assert enc.state == EnclaveState.INITIALIZED

    def test_initialize_twice(self):
        enc = Enclave("test")
        enc.initialize()
        with pytest.raises(SGXEnclaveCreationError):
            enc.initialize()

    def test_run(self):
        enc = Enclave("test")
        enc.initialize()
        enc.run()
        assert enc.state == EnclaveState.RUNNING

    def test_destroy(self):
        enc = _make_enclave()
        enc.destroy()
        assert enc.state == EnclaveState.DESTROYED

    def test_identity(self):
        enc = Enclave("test")
        assert len(enc.identity.mrenclave) == 64  # SHA-256 hex
        assert len(enc.identity.mrsigner) == 64


# =========================================================================
# ECALL Bridge
# =========================================================================

class TestECall:
    def test_register_and_invoke(self):
        enc = _make_enclave()
        enc.register_ecall(0, "greet", lambda name: f"Hello, {name}")
        result = enc.invoke_ecall(0, "FizzBuzz")
        assert result == "Hello, FizzBuzz"

    def test_invoke_not_running(self):
        enc = Enclave("test")
        enc.initialize()
        enc.register_ecall(0, "test")
        with pytest.raises(SGXECallError):
            enc.invoke_ecall(0)

    def test_invoke_unregistered(self):
        enc = _make_enclave()
        with pytest.raises(SGXECallError):
            enc.invoke_ecall(99)

    def test_call_count(self):
        enc = _make_enclave()
        enc.register_ecall(0, "noop", lambda: None)
        enc.invoke_ecall(0)
        enc.invoke_ecall(0)
        assert enc._ecalls[0].call_count == 2


# =========================================================================
# OCALL Bridge
# =========================================================================

class TestOCall:
    def test_register_and_invoke(self):
        enc = _make_enclave()
        results = []
        enc.register_ocall(0, "log", lambda msg: results.append(msg))
        enc.invoke_ocall(0, "event")
        assert results == ["event"]

    def test_invoke_unregistered(self):
        enc = _make_enclave()
        with pytest.raises(SGXOCallError):
            enc.invoke_ocall(99)


# =========================================================================
# Sealed Storage
# =========================================================================

class TestSealedStorage:
    def test_seal_and_unseal(self):
        enc = _make_enclave()
        storage = SGXSealedStorage()
        blob_id = storage.seal("enc1", enc.identity, b"secret data")
        result = storage.unseal(blob_id, enc.identity)
        assert result == b"secret data"

    def test_seal_empty_data(self):
        storage = SGXSealedStorage()
        enc = _make_enclave()
        with pytest.raises(SGXSealError):
            storage.seal("enc1", enc.identity, b"")

    def test_unseal_wrong_identity(self):
        enc1 = Enclave("enc1")
        enc2 = Enclave("enc2")
        storage = SGXSealedStorage()
        blob_id = storage.seal("enc1", enc1.identity, b"secret")
        with pytest.raises(SGXMeasurementError):
            storage.unseal(blob_id, enc2.identity)

    def test_unseal_missing_blob(self):
        storage = SGXSealedStorage()
        enc = _make_enclave()
        with pytest.raises(SGXSealError):
            storage.unseal(999, enc.identity)

    def test_seal_mrsigner_policy(self):
        enc = _make_enclave()
        storage = SGXSealedStorage()
        blob_id = storage.seal(
            "enc1", enc.identity, b"data",
            policy=SealPolicy.MRSIGNER,
        )
        result = storage.unseal(blob_id, enc.identity)
        assert result == b"data"


# =========================================================================
# Attestation Engine
# =========================================================================

class TestAttestationEngine:
    def test_generate_quote(self):
        enc = _make_enclave()
        engine = AttestationEngine()
        quote = engine.generate_quote("enc1", enc.identity, b"report")
        assert quote.mrenclave == enc.identity.mrenclave
        assert len(quote.signature) == 64

    def test_verify_quote(self):
        enc = _make_enclave()
        engine = AttestationEngine()
        quote = engine.generate_quote("enc1", enc.identity, b"data")
        assert engine.verify_quote(quote) is True

    def test_verify_wrong_mrenclave(self):
        enc = _make_enclave()
        engine = AttestationEngine()
        quote = engine.generate_quote("enc1", enc.identity, b"data")
        with pytest.raises(SGXAttestationError):
            engine.verify_quote(quote, expected_mrenclave="wrong" * 8)

    def test_generate_empty_enclave_id(self):
        enc = _make_enclave()
        engine = AttestationEngine()
        with pytest.raises(SGXAttestationError):
            engine.generate_quote("", enc.identity)


# =========================================================================
# Memory Encryption Engine
# =========================================================================

class TestMemoryEncryption:
    def test_encrypt_decrypt(self):
        mee = MemoryEncryptionEngine()
        plaintext = b"FizzBuzz classification result"
        mee.encrypt_page(0x1000, plaintext)
        result = mee.decrypt_page(0x1000)
        assert result == plaintext

    def test_decrypt_missing_page(self):
        mee = MemoryEncryptionEngine()
        with pytest.raises(SGXMemoryError):
            mee.decrypt_page(0x9999)

    def test_page_count(self):
        mee = MemoryEncryptionEngine()
        mee.encrypt_page(0x1000, b"a")
        mee.encrypt_page(0x2000, b"b")
        assert mee.page_count == 2

    def test_eviction_count(self):
        mee = MemoryEncryptionEngine()
        mee.encrypt_page(0x1000, b"a")
        mee.encrypt_page(0x1000, b"b")  # re-encrypt same page
        assert mee.eviction_count == 2


# =========================================================================
# SGX Platform
# =========================================================================

class TestSGXPlatform:
    def test_create_enclave(self):
        platform = SGXPlatform()
        enc = platform.create_enclave("test")
        assert platform.enclave_count == 1

    def test_create_duplicate(self):
        platform = SGXPlatform()
        platform.create_enclave("test")
        with pytest.raises(SGXEnclaveCreationError):
            platform.create_enclave("test")

    def test_destroy_enclave(self):
        platform = SGXPlatform()
        platform.create_enclave("test")
        platform.destroy_enclave("test")
        assert platform.enclave_count == 0

    def test_destroy_missing(self):
        platform = SGXPlatform()
        with pytest.raises(SGXEnclaveCreationError):
            platform.destroy_enclave("missing")

    def test_get_stats(self):
        platform = SGXPlatform()
        stats = platform.get_stats()
        assert stats["version"] == FIZZSGX_VERSION


# =========================================================================
# Dashboard
# =========================================================================

class TestDashboard:
    def test_render(self):
        platform = SGXPlatform()
        output = SGXDashboard.render(platform)
        assert "FizzSGX" in output
        assert "Enclave" in output


# =========================================================================
# Middleware
# =========================================================================

class TestMiddleware:
    def test_process_fizz(self):
        platform, mw = create_fizzsgx_subsystem()
        ctx = ProcessingContext(number=3)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["sgx_classification"] == "Fizz"

    def test_process_buzz(self):
        platform, mw = create_fizzsgx_subsystem()
        ctx = ProcessingContext(number=5)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["sgx_classification"] == "Buzz"

    def test_process_fizzbuzz(self):
        platform, mw = create_fizzsgx_subsystem()
        ctx = ProcessingContext(number=30)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["sgx_classification"] == "FizzBuzz"

    def test_process_number(self):
        platform, mw = create_fizzsgx_subsystem()
        ctx = ProcessingContext(number=7)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["sgx_classification"] == "7"

    def test_enclave_created_lazily(self):
        platform, mw = create_fizzsgx_subsystem()
        assert platform.enclave_count == 0
        ctx = ProcessingContext(number=1)
        mw.process(ctx, lambda c: c)
        assert platform.enclave_count == 1

    def test_get_name(self):
        _, mw = create_fizzsgx_subsystem()
        assert mw.get_name() == "fizzsgx"

    def test_get_priority(self):
        _, mw = create_fizzsgx_subsystem()
        assert mw.get_priority() == 249


# =========================================================================
# Factory
# =========================================================================

class TestFactory:
    def test_create_subsystem(self):
        platform, mw = create_fizzsgx_subsystem(enclave_size=32 * 1024 * 1024)
        assert platform.enclave_size == 32 * 1024 * 1024
        assert mw.platform is platform

"""
Enterprise FizzBuzz Platform - FizzSGX Intel SGX Enclave Simulator

Implements a simulator for Intel Software Guard Extensions (SGX),
providing secure enclave creation, ECALL/OCALL bridge, sealed storage,
remote attestation, and memory encryption engine for secure FizzBuzz
classification within trusted execution environments.

SGX provides hardware-enforced isolation for sensitive computation.
The FizzSGX subsystem models the SGX architecture:

    SGXPlatform
        ├── EnclaveManager        (enclave lifecycle management)
        │     ├── CreateEnclave   (ECREATE + EADD + EINIT)
        │     ├── DestroyEnclave  (EREMOVE)
        │     └── EnclaveState    (INITIALIZED, RUNNING, DESTROYED)
        ├── ECallBridge           (untrusted → trusted transitions)
        │     ├── RegisterECall   (define enclave entry points)
        │     └── InvokeECall     (call into enclave)
        ├── OCallBridge           (trusted → untrusted transitions)
        │     ├── RegisterOCall   (define host callbacks)
        │     └── InvokeOCall     (call out of enclave)
        ├── SealedStorage         (enclave-bound data encryption)
        │     ├── SealData        (encrypt with enclave identity)
        │     └── UnsealData      (decrypt with enclave identity)
        ├── AttestationEngine     (remote attestation quotes)
        │     ├── GenerateQuote   (SGX REPORT → QUOTE)
        │     └── VerifyQuote     (validate attestation evidence)
        └── MemoryEncryption      (MEE for enclave page cache)

FizzBuzz classification is executed inside an SGX enclave, ensuring
that the classification logic and results are protected from
privileged software including the OS and hypervisor.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

FIZZSGX_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 249

DEFAULT_ENCLAVE_SIZE = 67108864  # 64 MB
MAX_ENCLAVES = 8
MAX_ECALLS = 256
MAX_OCALLS = 256
MAX_SEALED_BLOBS = 1024
MEASUREMENT_SIZE = 32  # SHA-256


# ============================================================================
# Enums
# ============================================================================

class EnclaveState(Enum):
    """SGX enclave lifecycle states."""
    CREATED = "created"
    INITIALIZED = "initialized"
    RUNNING = "running"
    SUSPENDED = "suspended"
    DESTROYED = "destroyed"


class SealPolicy(Enum):
    """Data sealing policies."""
    MRENCLAVE = "mrenclave"  # Sealed to enclave identity
    MRSIGNER = "mrsigner"   # Sealed to signer identity


class AttestationType(Enum):
    """Attestation types."""
    LOCAL = "local"
    REMOTE = "remote"
    DCAP = "dcap"


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class EnclaveIdentity:
    """Enclave measurement identity."""
    mrenclave: str  # SHA-256 of enclave code/data
    mrsigner: str   # SHA-256 of enclave signer
    isv_prod_id: int = 0
    isv_svn: int = 0


@dataclass
class ECallDefinition:
    """Enclave call (ECALL) entry point."""
    function_id: int
    name: str
    handler: Optional[Callable] = None
    call_count: int = 0


@dataclass
class OCallDefinition:
    """Out-call (OCALL) from enclave to host."""
    function_id: int
    name: str
    handler: Optional[Callable] = None
    call_count: int = 0


@dataclass
class SealedBlob:
    """Data sealed to an enclave identity."""
    blob_id: int
    policy: SealPolicy
    enclave_id: str
    identity_hash: str
    ciphertext: bytes
    additional_data: bytes = b""
    timestamp: float = 0.0


@dataclass
class AttestationQuote:
    """SGX attestation quote."""
    enclave_id: str
    mrenclave: str
    mrsigner: str
    report_data: bytes
    nonce: bytes
    signature: str
    timestamp: float = 0.0


@dataclass
class EnclavePage:
    """Encrypted enclave page in the Enclave Page Cache."""
    page_address: int
    encrypted_data: bytes
    mac: bytes
    version: int = 0


# ============================================================================
# Memory Encryption Engine
# ============================================================================

class MemoryEncryptionEngine:
    """SGX Memory Encryption Engine (MEE).

    Encrypts enclave pages as they are evicted from the processor
    cache and decrypts them on reload. Each page has an associated
    MAC for integrity verification and a version counter for
    replay protection.
    """

    def __init__(self) -> None:
        self._key = secrets.token_bytes(32)
        self._pages: dict[int, EnclavePage] = {}
        self._evictions = 0
        self._reloads = 0

    def encrypt_page(self, address: int, plaintext: bytes) -> EnclavePage:
        """Encrypt an enclave page."""
        h = hashlib.sha256()
        h.update(self._key)
        h.update(plaintext)
        h.update(address.to_bytes(8, "little"))
        mac = h.digest()[:16]

        # XOR-based stream cipher (simplified MEE)
        key_stream = hashlib.sha256(self._key + address.to_bytes(8, "little")).digest()
        encrypted = bytes(b ^ key_stream[i % len(key_stream)] for i, b in enumerate(plaintext))

        version = 0
        if address in self._pages:
            version = self._pages[address].version + 1

        page = EnclavePage(
            page_address=address,
            encrypted_data=encrypted,
            mac=mac,
            version=version,
        )
        self._pages[address] = page
        self._evictions += 1
        return page

    def decrypt_page(self, address: int) -> bytes:
        """Decrypt an enclave page."""
        from enterprise_fizzbuzz.domain.exceptions.fizzsgx import SGXMemoryError

        if address not in self._pages:
            raise SGXMemoryError(address, 0, "page not found in EPC")

        page = self._pages[address]
        key_stream = hashlib.sha256(self._key + address.to_bytes(8, "little")).digest()
        plaintext = bytes(b ^ key_stream[i % len(key_stream)] for i, b in enumerate(page.encrypted_data))

        # Verify MAC
        h = hashlib.sha256()
        h.update(self._key)
        h.update(plaintext)
        h.update(address.to_bytes(8, "little"))
        expected_mac = h.digest()[:16]

        if expected_mac != page.mac:
            raise SGXMemoryError(address, len(page.encrypted_data), "MAC verification failed")

        self._reloads += 1
        return plaintext

    @property
    def page_count(self) -> int:
        return len(self._pages)

    @property
    def eviction_count(self) -> int:
        return self._evictions


# ============================================================================
# Sealed Storage
# ============================================================================

class SGXSealedStorage:
    """SGX sealed storage for enclave-bound data encryption.

    Data is sealed (encrypted) using a key derived from the enclave's
    identity (MRENCLAVE or MRSIGNER). Only the same enclave (or a
    signer-equivalent enclave) can unseal the data.
    """

    def __init__(self) -> None:
        self._blobs: dict[int, SealedBlob] = {}
        self._next_id = 0

    def seal(
        self,
        enclave_id: str,
        identity: EnclaveIdentity,
        data: bytes,
        policy: SealPolicy = SealPolicy.MRENCLAVE,
        additional_data: bytes = b"",
    ) -> int:
        """Seal data to an enclave identity."""
        from enterprise_fizzbuzz.domain.exceptions.fizzsgx import SGXSealError

        if not data:
            raise SGXSealError("cannot seal empty data")

        if len(self._blobs) >= MAX_SEALED_BLOBS:
            raise SGXSealError("maximum sealed blobs reached")

        identity_hash = identity.mrenclave if policy == SealPolicy.MRENCLAVE else identity.mrsigner

        # Derive sealing key
        seal_key = hashlib.sha256(
            identity_hash.encode() + policy.value.encode()
        ).digest()

        # Encrypt data
        ciphertext = bytes(
            b ^ seal_key[i % len(seal_key)] for i, b in enumerate(data)
        )

        blob_id = self._next_id
        self._next_id += 1

        self._blobs[blob_id] = SealedBlob(
            blob_id=blob_id,
            policy=policy,
            enclave_id=enclave_id,
            identity_hash=identity_hash,
            ciphertext=ciphertext,
            additional_data=additional_data,
            timestamp=time.monotonic(),
        )

        return blob_id

    def unseal(
        self,
        blob_id: int,
        identity: EnclaveIdentity,
    ) -> bytes:
        """Unseal data using the enclave identity."""
        from enterprise_fizzbuzz.domain.exceptions.fizzsgx import SGXSealError

        if blob_id not in self._blobs:
            raise SGXSealError(f"blob {blob_id} not found")

        blob = self._blobs[blob_id]

        # Check identity match
        if blob.policy == SealPolicy.MRENCLAVE:
            current_hash = identity.mrenclave
        else:
            current_hash = identity.mrsigner

        if current_hash != blob.identity_hash:
            from enterprise_fizzbuzz.domain.exceptions.fizzsgx import SGXMeasurementError
            raise SGXMeasurementError(blob.identity_hash, current_hash)

        # Derive sealing key
        seal_key = hashlib.sha256(
            blob.identity_hash.encode() + blob.policy.value.encode()
        ).digest()

        # Decrypt
        plaintext = bytes(
            b ^ seal_key[i % len(seal_key)] for i, b in enumerate(blob.ciphertext)
        )

        return plaintext

    @property
    def blob_count(self) -> int:
        return len(self._blobs)


# ============================================================================
# Attestation Engine
# ============================================================================

class AttestationEngine:
    """SGX remote attestation engine.

    Generates attestation quotes that cryptographically prove the
    identity and integrity of an enclave to a remote verifier.
    """

    def __init__(self) -> None:
        self._signing_key = secrets.token_bytes(32)
        self._quotes_generated = 0

    def generate_quote(
        self,
        enclave_id: str,
        identity: EnclaveIdentity,
        report_data: bytes = b"",
        nonce: Optional[bytes] = None,
    ) -> AttestationQuote:
        """Generate an attestation quote."""
        from enterprise_fizzbuzz.domain.exceptions.fizzsgx import SGXAttestationError

        if not enclave_id:
            raise SGXAttestationError("", "enclave ID is required")

        actual_nonce = nonce or secrets.token_bytes(32)

        # Compute quote signature
        h = hashlib.sha256()
        h.update(identity.mrenclave.encode())
        h.update(identity.mrsigner.encode())
        h.update(report_data)
        h.update(actual_nonce)
        h.update(self._signing_key)
        signature = h.hexdigest()

        self._quotes_generated += 1

        return AttestationQuote(
            enclave_id=enclave_id,
            mrenclave=identity.mrenclave,
            mrsigner=identity.mrsigner,
            report_data=report_data,
            nonce=actual_nonce,
            signature=signature,
            timestamp=time.monotonic(),
        )

    def verify_quote(self, quote: AttestationQuote, expected_mrenclave: Optional[str] = None) -> bool:
        """Verify an attestation quote."""
        from enterprise_fizzbuzz.domain.exceptions.fizzsgx import SGXAttestationError

        if expected_mrenclave and quote.mrenclave != expected_mrenclave:
            raise SGXAttestationError(
                quote.enclave_id,
                f"MRENCLAVE mismatch: expected {expected_mrenclave[:16]}...",
            )

        # Re-compute signature
        h = hashlib.sha256()
        h.update(quote.mrenclave.encode())
        h.update(quote.mrsigner.encode())
        h.update(quote.report_data)
        h.update(quote.nonce)
        h.update(self._signing_key)
        expected_sig = h.hexdigest()

        if expected_sig != quote.signature:
            raise SGXAttestationError(quote.enclave_id, "quote signature invalid")

        return True

    @property
    def quotes_generated(self) -> int:
        return self._quotes_generated


# ============================================================================
# Enclave
# ============================================================================

class Enclave:
    """An SGX enclave instance."""

    def __init__(
        self,
        enclave_id: str,
        size: int = DEFAULT_ENCLAVE_SIZE,
        code_hash: Optional[str] = None,
        signer_hash: Optional[str] = None,
    ) -> None:
        self.enclave_id = enclave_id
        self.size = size
        self._state = EnclaveState.CREATED
        self.identity = EnclaveIdentity(
            mrenclave=code_hash or hashlib.sha256(enclave_id.encode()).hexdigest(),
            mrsigner=signer_hash or hashlib.sha256(b"fizzbuzz-signer").hexdigest(),
        )
        self._ecalls: dict[int, ECallDefinition] = {}
        self._ocalls: dict[int, OCallDefinition] = {}
        self._heap_used = 0

    def initialize(self) -> None:
        """Initialize the enclave (EINIT)."""
        from enterprise_fizzbuzz.domain.exceptions.fizzsgx import SGXEnclaveCreationError

        if self._state != EnclaveState.CREATED:
            raise SGXEnclaveCreationError(
                self.enclave_id,
                f"cannot initialize from state {self._state.value}",
            )
        self._state = EnclaveState.INITIALIZED

    def run(self) -> None:
        """Transition to running state."""
        if self._state == EnclaveState.INITIALIZED:
            self._state = EnclaveState.RUNNING

    def destroy(self) -> None:
        """Destroy the enclave (EREMOVE)."""
        self._state = EnclaveState.DESTROYED

    def register_ecall(self, function_id: int, name: str, handler: Optional[Callable] = None) -> None:
        """Register an ECALL entry point."""
        from enterprise_fizzbuzz.domain.exceptions.fizzsgx import SGXECallError

        if len(self._ecalls) >= MAX_ECALLS:
            raise SGXECallError(function_id, "maximum ECALLs reached")

        self._ecalls[function_id] = ECallDefinition(
            function_id=function_id, name=name, handler=handler,
        )

    def invoke_ecall(self, function_id: int, *args: Any) -> Any:
        """Invoke an ECALL into the enclave."""
        from enterprise_fizzbuzz.domain.exceptions.fizzsgx import SGXECallError

        if self._state != EnclaveState.RUNNING:
            raise SGXECallError(
                function_id,
                f"enclave not running (state: {self._state.value})",
            )

        if function_id not in self._ecalls:
            raise SGXECallError(function_id, "ECALL not registered")

        ecall = self._ecalls[function_id]
        ecall.call_count += 1

        if ecall.handler:
            return ecall.handler(*args)
        return None

    def register_ocall(self, function_id: int, name: str, handler: Optional[Callable] = None) -> None:
        """Register an OCALL callback."""
        from enterprise_fizzbuzz.domain.exceptions.fizzsgx import SGXOCallError

        if len(self._ocalls) >= MAX_OCALLS:
            raise SGXOCallError(function_id, "maximum OCALLs reached")

        self._ocalls[function_id] = OCallDefinition(
            function_id=function_id, name=name, handler=handler,
        )

    def invoke_ocall(self, function_id: int, *args: Any) -> Any:
        """Invoke an OCALL from the enclave."""
        from enterprise_fizzbuzz.domain.exceptions.fizzsgx import SGXOCallError

        if function_id not in self._ocalls:
            raise SGXOCallError(function_id, "OCALL not registered")

        ocall = self._ocalls[function_id]
        ocall.call_count += 1

        if ocall.handler:
            return ocall.handler(*args)
        return None

    @property
    def state(self) -> EnclaveState:
        return self._state

    @property
    def ecall_count(self) -> int:
        return len(self._ecalls)

    @property
    def ocall_count(self) -> int:
        return len(self._ocalls)


# ============================================================================
# SGX Platform
# ============================================================================

class SGXPlatform:
    """Top-level SGX platform aggregating all subsystems."""

    def __init__(self, enclave_size: int = DEFAULT_ENCLAVE_SIZE) -> None:
        self.enclave_size = enclave_size
        self.sealed_storage = SGXSealedStorage()
        self.attestation_engine = AttestationEngine()
        self.memory_encryption = MemoryEncryptionEngine()
        self._enclaves: dict[str, Enclave] = {}

    def create_enclave(
        self,
        enclave_id: str,
        code_hash: Optional[str] = None,
        signer_hash: Optional[str] = None,
    ) -> Enclave:
        """Create a new SGX enclave."""
        from enterprise_fizzbuzz.domain.exceptions.fizzsgx import SGXEnclaveCreationError

        if enclave_id in self._enclaves:
            raise SGXEnclaveCreationError(enclave_id, "enclave already exists")

        if len(self._enclaves) >= MAX_ENCLAVES:
            raise SGXEnclaveCreationError(enclave_id, "maximum enclaves reached")

        enclave = Enclave(
            enclave_id=enclave_id,
            size=self.enclave_size,
            code_hash=code_hash,
            signer_hash=signer_hash,
        )
        self._enclaves[enclave_id] = enclave
        logger.info("SGX enclave created: %s", enclave_id)
        return enclave

    def destroy_enclave(self, enclave_id: str) -> None:
        """Destroy an enclave."""
        from enterprise_fizzbuzz.domain.exceptions.fizzsgx import SGXEnclaveCreationError

        if enclave_id not in self._enclaves:
            raise SGXEnclaveCreationError(enclave_id, "enclave not found")

        self._enclaves[enclave_id].destroy()
        del self._enclaves[enclave_id]

    def get_enclave(self, enclave_id: str) -> Enclave:
        from enterprise_fizzbuzz.domain.exceptions.fizzsgx import SGXEnclaveCreationError

        if enclave_id not in self._enclaves:
            raise SGXEnclaveCreationError(enclave_id, "enclave not found")
        return self._enclaves[enclave_id]

    @property
    def enclave_count(self) -> int:
        return len(self._enclaves)

    def get_stats(self) -> dict:
        return {
            "version": FIZZSGX_VERSION,
            "enclaves": self.enclave_count,
            "enclave_size": self.enclave_size,
            "sealed_blobs": self.sealed_storage.blob_count,
            "attestation_quotes": self.attestation_engine.quotes_generated,
            "encrypted_pages": self.memory_encryption.page_count,
            "page_evictions": self.memory_encryption.eviction_count,
        }


# ============================================================================
# Dashboard
# ============================================================================

class SGXDashboard:
    """ASCII dashboard for SGX platform visualization."""

    @staticmethod
    def render(platform: SGXPlatform, width: int = 72) -> str:
        lines = []
        border = "=" * width
        lines.append(border)
        lines.append("  FizzSGX Intel SGX Enclave Simulator Dashboard".center(width))
        lines.append(border)

        stats = platform.get_stats()
        lines.append(f"  Version: {stats['version']}")
        lines.append(f"  Enclaves: {stats['enclaves']}")
        lines.append(f"  Enclave size: {stats['enclave_size']} bytes")
        lines.append(f"  Sealed blobs: {stats['sealed_blobs']}")
        lines.append(f"  Attestation quotes: {stats['attestation_quotes']}")
        lines.append(f"  Encrypted pages: {stats['encrypted_pages']}")
        lines.append(f"  Page evictions: {stats['page_evictions']}")
        lines.append(border)
        return "\n".join(lines)


# ============================================================================
# Middleware
# ============================================================================

class SGXMiddleware(IMiddleware):
    """Middleware that executes FizzBuzz classification inside an SGX enclave.

    Each classification is performed as an ECALL into the FizzBuzz
    enclave, ensuring that the classification logic and results are
    protected by SGX memory encryption.
    """

    def __init__(self, platform: SGXPlatform) -> None:
        self.platform = platform
        self.evaluations = 0
        self._enclave: Optional[Enclave] = None

    def _ensure_enclave(self) -> Enclave:
        """Lazily create and initialize the FizzBuzz classification enclave."""
        if self._enclave is None or self._enclave.state == EnclaveState.DESTROYED:
            self._enclave = self.platform.create_enclave("fizzbuzz-enclave")
            self._enclave.initialize()
            self._enclave.run()

            # Register the FizzBuzz classification ECALL
            def classify(n: int) -> str:
                if n % 15 == 0:
                    return "FizzBuzz"
                elif n % 3 == 0:
                    return "Fizz"
                elif n % 5 == 0:
                    return "Buzz"
                return str(n)

            self._enclave.register_ecall(0, "fizzbuzz_classify", classify)

        return self._enclave

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        number = context.number
        self.evaluations += 1

        enclave = self._ensure_enclave()
        label = enclave.invoke_ecall(0, number)

        context.metadata["sgx_classification"] = label
        context.metadata["sgx_enclave_id"] = enclave.enclave_id
        context.metadata["sgx_enabled"] = True

        return next_handler(context)

    def get_name(self) -> str:
        return "fizzsgx"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Factory
# ============================================================================

def create_fizzsgx_subsystem(
    enclave_size: int = DEFAULT_ENCLAVE_SIZE,
) -> tuple[SGXPlatform, SGXMiddleware]:
    """Create and configure the complete FizzSGX subsystem.

    Args:
        enclave_size: Maximum enclave memory size in bytes.

    Returns:
        Tuple of (SGXPlatform, SGXMiddleware).
    """
    platform = SGXPlatform(enclave_size=enclave_size)
    middleware = SGXMiddleware(platform)

    logger.info(
        "FizzSGX subsystem initialized: enclave_size=%d bytes",
        enclave_size,
    )

    return platform, middleware

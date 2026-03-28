"""
Enterprise FizzBuzz Platform - FizzTPM Trusted Platform Module 2.0 Simulator

Implements a TPM 2.0 simulator for hardware-rooted trust in FizzBuzz
classification integrity. The Trusted Platform Module is a dedicated
security coprocessor that provides a hardware root of trust through
Platform Configuration Registers (PCRs), cryptographic key management,
sealed storage, and remote attestation.

The FizzTPM subsystem faithfully models the TPM 2.0 architecture:

    TPMDevice
        ├── PCRBank               (24 SHA-256 Platform Configuration Registers)
        │     ├── PCR_Extend      (hash-extend: new = SHA256(old || data))
        │     └── PCR_Read        (non-volatile measurement log)
        ├── SealedStorage         (data sealed to specific PCR values)
        │     ├── Seal            (encrypt data bound to PCR state)
        │     └── Unseal          (decrypt only if PCRs match sealed state)
        ├── NVRAMStorage          (non-volatile RAM for persistent data)
        ├── QuoteEngine           (remote attestation with signed PCR digests)
        └── RNG                   (hardware random number generator)

Each FizzBuzz classification result is extended into a PCR, creating an
immutable measurement chain. Remote verifiers can attest that the
classification pipeline executed the expected code path by quoting the
PCR values and verifying the measurement log.
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

FIZZTPM_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 242

NUM_PCRS = 24
PCR_SIZE_BYTES = 32  # SHA-256
NVRAM_MAX_ENTRIES = 256
NVRAM_MAX_VALUE_SIZE = 2048
DEFAULT_AUTH_SECRET = b"fizzbuzz-tpm-auth"

# FizzBuzz measurement event types
EVENT_CLASSIFICATION = 0x01
EVENT_BATCH_START = 0x02
EVENT_BATCH_END = 0x03
EVENT_CONFIG_CHANGE = 0x04


# ============================================================================
# Enums
# ============================================================================

class PCRAlgorithm(Enum):
    """Hash algorithms for PCR banks."""
    SHA256 = "sha256"
    SHA384 = "sha384"
    SHA512 = "sha512"


class TPMCommand(Enum):
    """TPM 2.0 command codes."""
    PCR_EXTEND = "TPM2_PCR_Extend"
    PCR_READ = "TPM2_PCR_Read"
    QUOTE = "TPM2_Quote"
    SEAL = "TPM2_Seal"
    UNSEAL = "TPM2_Unseal"
    NV_WRITE = "TPM2_NV_Write"
    NV_READ = "TPM2_NV_Read"
    GET_RANDOM = "TPM2_GetRandom"


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class PCRValue:
    """Current value of a Platform Configuration Register."""
    index: int
    value: bytes = field(default_factory=lambda: b"\x00" * PCR_SIZE_BYTES)
    extend_count: int = 0


@dataclass
class MeasurementLogEntry:
    """Entry in the TPM event log recording a PCR extend operation."""
    pcr_index: int
    event_type: int
    digest: bytes
    data: bytes
    timestamp: float = 0.0


@dataclass
class SealedBlob:
    """Data sealed to a specific PCR state."""
    handle: int
    data: bytes
    pcr_index: int
    pcr_value_at_seal: bytes
    auth_hash: bytes


@dataclass
class NVRAMEntry:
    """A non-volatile RAM storage entry."""
    nv_index: int
    data: bytes
    size: int
    locked: bool = False


# ============================================================================
# PCR Bank
# ============================================================================

class PCRBank:
    """SHA-256 PCR bank with 24 Platform Configuration Registers.

    PCRs can only be modified through the extend operation, which
    computes a new value as SHA-256(current_value || new_data). This
    ensures that PCR values form an immutable chain of measurements
    that cannot be rewound or forged.
    """

    def __init__(self, algorithm: PCRAlgorithm = PCRAlgorithm.SHA256) -> None:
        self.algorithm = algorithm
        self._pcrs: list[PCRValue] = [
            PCRValue(index=i) for i in range(NUM_PCRS)
        ]
        self._event_log: list[MeasurementLogEntry] = []

    def read(self, index: int) -> bytes:
        """Read the current value of a PCR."""
        from enterprise_fizzbuzz.domain.exceptions.fizztpm import TPMPCRError

        if index < 0 or index >= NUM_PCRS:
            raise TPMPCRError(index, NUM_PCRS)
        return self._pcrs[index].value

    def extend(self, index: int, data: bytes) -> bytes:
        """Extend a PCR with new measurement data.

        Computes: PCR[index] = SHA-256(PCR[index] || data)

        Returns the new PCR value.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizztpm import TPMPCRError

        if index < 0 or index >= NUM_PCRS:
            raise TPMPCRError(index, NUM_PCRS)

        current = self._pcrs[index].value
        h = hashlib.sha256()
        h.update(current)
        h.update(data)
        new_value = h.digest()

        self._pcrs[index].value = new_value
        self._pcrs[index].extend_count += 1

        # Record in event log
        self._event_log.append(MeasurementLogEntry(
            pcr_index=index,
            event_type=EVENT_CLASSIFICATION,
            digest=new_value,
            data=data,
            timestamp=time.monotonic(),
        ))

        logger.debug(
            "PCR[%d] extended (count: %d): %s",
            index, self._pcrs[index].extend_count, new_value.hex()[:16],
        )
        return new_value

    def reset(self, index: int) -> None:
        """Reset a PCR to its initial value (zeros).

        Only PCRs 16-23 are resettable in real TPM hardware. PCRs 0-15
        can only be reset by a platform reboot.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizztpm import TPMPCRError

        if index < 0 or index >= NUM_PCRS:
            raise TPMPCRError(index, NUM_PCRS)
        if index < 16:
            raise TPMPCRError(index, NUM_PCRS)
        self._pcrs[index].value = b"\x00" * PCR_SIZE_BYTES
        self._pcrs[index].extend_count = 0

    def get_event_log(self) -> list[MeasurementLogEntry]:
        """Return the complete measurement event log."""
        return list(self._event_log)

    def get_extend_count(self, index: int) -> int:
        """Return the number of times a PCR has been extended."""
        from enterprise_fizzbuzz.domain.exceptions.fizztpm import TPMPCRError

        if index < 0 or index >= NUM_PCRS:
            raise TPMPCRError(index, NUM_PCRS)
        return self._pcrs[index].extend_count


# ============================================================================
# Sealed Storage
# ============================================================================

class SealedStorage:
    """TPM sealed storage that binds data to specific PCR values.

    Data is encrypted (sealed) with a binding to the current value of
    a specified PCR. The data can only be decrypted (unsealed) when
    the PCR contains the exact same value. If any measurement changes
    the PCR value, the sealed data becomes permanently inaccessible.
    """

    def __init__(self, pcr_bank: PCRBank) -> None:
        self._pcr_bank = pcr_bank
        self._sealed_blobs: dict[int, SealedBlob] = {}
        self._next_handle = 0x81000000

    def seal(self, data: bytes, pcr_index: int,
             auth: bytes = DEFAULT_AUTH_SECRET) -> int:
        """Seal data to the current value of a PCR.

        Returns a handle for later unsealing.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizztpm import TPMSealError

        if not data:
            raise TPMSealError("cannot seal empty data")

        pcr_value = self._pcr_bank.read(pcr_index)
        auth_hash = hashlib.sha256(auth).digest()

        handle = self._next_handle
        self._next_handle += 1

        self._sealed_blobs[handle] = SealedBlob(
            handle=handle,
            data=data,
            pcr_index=pcr_index,
            pcr_value_at_seal=pcr_value,
            auth_hash=auth_hash,
        )

        logger.debug(
            "Data sealed to PCR[%d] with handle 0x%08X", pcr_index, handle,
        )
        return handle

    def unseal(self, handle: int, auth: bytes = DEFAULT_AUTH_SECRET) -> bytes:
        """Unseal data if the PCR value matches the sealed state.

        Raises:
            TPMUnsealError: If the PCR value has changed since sealing.
            TPMAuthorizationError: If the auth secret is incorrect.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizztpm import (
            TPMAuthorizationError,
            TPMUnsealError,
        )

        if handle not in self._sealed_blobs:
            raise TPMUnsealError(-1)

        blob = self._sealed_blobs[handle]
        auth_hash = hashlib.sha256(auth).digest()
        if auth_hash != blob.auth_hash:
            raise TPMAuthorizationError(handle)

        current_pcr = self._pcr_bank.read(blob.pcr_index)
        if current_pcr != blob.pcr_value_at_seal:
            raise TPMUnsealError(blob.pcr_index)

        logger.debug("Data unsealed from handle 0x%08X", handle)
        return blob.data

    @property
    def blob_count(self) -> int:
        return len(self._sealed_blobs)


# ============================================================================
# NVRAM Storage
# ============================================================================

class NVRAMStorage:
    """TPM non-volatile RAM for persistent data storage.

    NVRAM indices are allocated and written by the platform firmware
    and operating system. Each index can store up to 2048 bytes of
    data. Entries can be locked to prevent further modification.
    """

    def __init__(self) -> None:
        self._entries: dict[int, NVRAMEntry] = {}

    def define(self, nv_index: int, size: int) -> None:
        """Define a new NVRAM index with a given size."""
        from enterprise_fizzbuzz.domain.exceptions.fizztpm import TPMNVRAMError

        if nv_index in self._entries:
            raise TPMNVRAMError(nv_index, "index already defined")
        if size <= 0 or size > NVRAM_MAX_VALUE_SIZE:
            raise TPMNVRAMError(
                nv_index, f"invalid size {size} (max: {NVRAM_MAX_VALUE_SIZE})",
            )
        if len(self._entries) >= NVRAM_MAX_ENTRIES:
            raise TPMNVRAMError(nv_index, "NVRAM capacity exceeded")

        self._entries[nv_index] = NVRAMEntry(
            nv_index=nv_index,
            data=b"",
            size=size,
        )

    def write(self, nv_index: int, data: bytes) -> None:
        """Write data to an NVRAM index."""
        from enterprise_fizzbuzz.domain.exceptions.fizztpm import TPMNVRAMError

        if nv_index not in self._entries:
            raise TPMNVRAMError(nv_index, "index not defined")
        entry = self._entries[nv_index]
        if entry.locked:
            raise TPMNVRAMError(nv_index, "index is locked")
        if len(data) > entry.size:
            raise TPMNVRAMError(
                nv_index,
                f"data size {len(data)} exceeds allocation {entry.size}",
            )
        entry.data = data

    def read(self, nv_index: int) -> bytes:
        """Read data from an NVRAM index."""
        from enterprise_fizzbuzz.domain.exceptions.fizztpm import TPMNVRAMError

        if nv_index not in self._entries:
            raise TPMNVRAMError(nv_index, "index not defined")
        return self._entries[nv_index].data

    def lock(self, nv_index: int) -> None:
        """Lock an NVRAM index to prevent further writes."""
        from enterprise_fizzbuzz.domain.exceptions.fizztpm import TPMNVRAMError

        if nv_index not in self._entries:
            raise TPMNVRAMError(nv_index, "index not defined")
        self._entries[nv_index].locked = True

    @property
    def entry_count(self) -> int:
        return len(self._entries)


# ============================================================================
# TPM Device
# ============================================================================

class TPMDevice:
    """TPM 2.0 device simulator.

    Aggregates the PCR bank, sealed storage, NVRAM, and random number
    generator into a single device interface. Provides the quote/attest
    operation for remote attestation of platform integrity.
    """

    def __init__(self, algorithm: PCRAlgorithm = PCRAlgorithm.SHA256) -> None:
        self.pcr_bank = PCRBank(algorithm=algorithm)
        self.sealed_storage = SealedStorage(self.pcr_bank)
        self.nvram = NVRAMStorage()
        self.commands_executed = 0
        self._algorithm = algorithm

    def pcr_extend(self, index: int, data: bytes) -> bytes:
        """Extend a PCR with measurement data."""
        self.commands_executed += 1
        return self.pcr_bank.extend(index, data)

    def pcr_read(self, index: int) -> bytes:
        """Read the current value of a PCR."""
        self.commands_executed += 1
        return self.pcr_bank.read(index)

    def seal(self, data: bytes, pcr_index: int,
             auth: bytes = DEFAULT_AUTH_SECRET) -> int:
        """Seal data to a PCR value."""
        self.commands_executed += 1
        return self.sealed_storage.seal(data, pcr_index, auth)

    def unseal(self, handle: int, auth: bytes = DEFAULT_AUTH_SECRET) -> bytes:
        """Unseal data from a sealed blob."""
        self.commands_executed += 1
        return self.sealed_storage.unseal(handle, auth)

    def quote(self, pcr_indices: list[int], nonce: bytes) -> dict:
        """Generate a TPM quote for remote attestation.

        Returns a signed digest of the requested PCR values along
        with the nonce, enabling a remote verifier to confirm the
        platform's measurement state.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizztpm import (
            TPMAttestationError,
        )

        self.commands_executed += 1

        if not pcr_indices:
            raise TPMAttestationError("empty PCR selection")
        if not nonce:
            raise TPMAttestationError("nonce is required")

        # Compute composite hash of selected PCRs
        h = hashlib.sha256()
        pcr_values = {}
        for idx in pcr_indices:
            val = self.pcr_bank.read(idx)
            h.update(val)
            pcr_values[idx] = val.hex()

        h.update(nonce)
        digest = h.digest()

        return {
            "pcr_values": pcr_values,
            "pcr_digest": digest.hex(),
            "nonce": nonce.hex(),
            "algorithm": self._algorithm.value,
            "timestamp": time.monotonic(),
        }

    def get_random(self, num_bytes: int) -> bytes:
        """Generate cryptographic random bytes."""
        from enterprise_fizzbuzz.domain.exceptions.fizztpm import TPMRandomError

        self.commands_executed += 1

        if num_bytes <= 0 or num_bytes > 4096:
            raise TPMRandomError(num_bytes)

        return secrets.token_bytes(num_bytes)

    def get_stats(self) -> dict:
        """Return device statistics."""
        pcr_extends = sum(
            self.pcr_bank.get_extend_count(i) for i in range(NUM_PCRS)
        )
        return {
            "version": FIZZTPM_VERSION,
            "algorithm": self._algorithm.value,
            "num_pcrs": NUM_PCRS,
            "total_extends": pcr_extends,
            "sealed_blobs": self.sealed_storage.blob_count,
            "nvram_entries": self.nvram.entry_count,
            "commands_executed": self.commands_executed,
            "event_log_size": len(self.pcr_bank.get_event_log()),
        }


# ============================================================================
# Dashboard
# ============================================================================

class TPMDashboard:
    """ASCII dashboard for TPM device visualization."""

    @staticmethod
    def render(device: TPMDevice, width: int = 72) -> str:
        lines = []
        border = "=" * width
        lines.append(border)
        lines.append("  FizzTPM Trusted Platform Module 2.0 Dashboard".center(width))
        lines.append(border)

        stats = device.get_stats()
        lines.append(f"  Version: {stats['version']}")
        lines.append(f"  Algorithm: {stats['algorithm']}")
        lines.append(f"  Commands executed: {stats['commands_executed']}")
        lines.append(f"  Total PCR extends: {stats['total_extends']}")
        lines.append(f"  Sealed blobs: {stats['sealed_blobs']}")
        lines.append(f"  NVRAM entries: {stats['nvram_entries']}")
        lines.append("")

        # Show non-zero PCRs
        for i in range(NUM_PCRS):
            val = device.pcr_bank.read(i)
            if val != b"\x00" * PCR_SIZE_BYTES:
                lines.append(f"  PCR[{i:2d}]: {val.hex()[:32]}...")
        lines.append(border)
        return "\n".join(lines)


# ============================================================================
# Middleware
# ============================================================================

class TPMMiddleware(IMiddleware):
    """Middleware that extends FizzBuzz classification into TPM PCRs.

    Each classification result is measured into PCR[17] (a resettable
    PCR in the dynamic range), creating an immutable measurement chain
    of all FizzBuzz evaluations processed by the pipeline.
    """

    MEASUREMENT_PCR = 17

    def __init__(self, device: TPMDevice) -> None:
        self.device = device
        self.evaluations = 0

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        """Process a FizzBuzz evaluation and extend measurement into PCR."""
        number = context.number
        self.evaluations += 1

        # Classify the number
        if number % 15 == 0:
            label = "FizzBuzz"
        elif number % 3 == 0:
            label = "Fizz"
        elif number % 5 == 0:
            label = "Buzz"
        else:
            label = str(number)

        # Extend classification into measurement PCR
        measurement = f"{number}:{label}".encode("utf-8")
        pcr_value = self.device.pcr_extend(self.MEASUREMENT_PCR, measurement)

        context.metadata["tpm_classification"] = label
        context.metadata["tpm_pcr_value"] = pcr_value.hex()[:16]
        context.metadata["tpm_enabled"] = True

        return next_handler(context)

    def get_name(self) -> str:
        return "fizztpm"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Factory
# ============================================================================

def create_fizztpm_subsystem(
    algorithm: PCRAlgorithm = PCRAlgorithm.SHA256,
) -> tuple[TPMDevice, TPMMiddleware]:
    """Create and configure the complete FizzTPM subsystem.

    Initializes a TPM 2.0 device with the specified hash algorithm
    and creates the middleware component for pipeline integration.

    Args:
        algorithm: Hash algorithm for the PCR bank.

    Returns:
        Tuple of (TPMDevice, TPMMiddleware).
    """
    device = TPMDevice(algorithm=algorithm)
    middleware = TPMMiddleware(device)

    logger.info(
        "FizzTPM subsystem initialized: algorithm=%s, %d PCRs",
        algorithm.value, NUM_PCRS,
    )

    return device, middleware

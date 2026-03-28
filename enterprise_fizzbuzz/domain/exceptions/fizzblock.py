"""
Enterprise FizzBuzz Platform - FizzBlock Block Storage Engine Errors (EFP-BLK00 .. EFP-BLK20)

Exception hierarchy for the FizzBlock block storage and volume management
engine.  Covers block device I/O, logical volume management (PV/VG/LV),
thin provisioning, copy-on-write snapshots, software RAID (levels 0/1/5/6/10),
I/O scheduling, AES-256-XTS block encryption, SHA-256 deduplication,
LZ4/zstd compression, QoS enforcement, FizzKube PersistentVolumeClaim
binding, online volume resize, and automated storage tiering.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FizzBlockError(FizzBuzzError):
    """Base exception for all FizzBlock block storage engine errors.

    FizzBlock is the platform's block storage subsystem that provides raw
    block device abstraction, logical volume management, and enterprise
    storage features including RAID, encryption, deduplication, compression,
    and QoS.  All block-storage-specific failures inherit from this class
    to enable categorical error handling in the middleware pipeline.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzBlock error: {reason}",
            error_code="EFP-BLK00",
            context={"reason": reason},
        )


class FizzBlockDeviceError(FizzBlockError):
    """Raised on block device errors.

    Covers failures in the block device abstraction layer including device
    initialization, metadata corruption, device state transitions, and
    block bitmap inconsistencies that prevent normal device operation.
    """

    def __init__(self, device_id: str, reason: str) -> None:
        super().__init__(f"Block device '{device_id}' error: {reason}")
        self.error_code = "EFP-BLK01"
        self.context = {"device_id": device_id, "reason": reason}


class FizzBlockIOError(FizzBlockError):
    """Raised on block I/O errors.

    Covers read and write failures at the block level including out-of-range
    block addresses, partial writes, I/O timeouts, and underlying storage
    medium errors that prevent completion of a block I/O request.
    """

    def __init__(self, device_id: str, block_offset: int, reason: str) -> None:
        super().__init__(f"I/O error on device '{device_id}' at block {block_offset}: {reason}")
        self.error_code = "EFP-BLK02"
        self.context = {"device_id": device_id, "block_offset": block_offset, "reason": reason}


class FizzBlockVolumeError(FizzBlockError):
    """Raised on logical volume errors.

    Covers failures in logical volume operations including extent mapping
    corruption, volume state machine violations, and metadata update
    failures that affect the integrity of the logical volume.
    """

    def __init__(self, volume_name: str, reason: str) -> None:
        super().__init__(f"Logical volume '{volume_name}' error: {reason}")
        self.error_code = "EFP-BLK03"
        self.context = {"volume_name": volume_name, "reason": reason}


class FizzBlockVolumeNotFoundError(FizzBlockError):
    """Raised when a logical volume is not found.

    The volume manager maintains a registry of all logical volumes across
    all volume groups.  This exception is raised when an operation
    references a volume name or UUID that does not exist in any known
    volume group.
    """

    def __init__(self, volume_name: str) -> None:
        super().__init__(f"Logical volume '{volume_name}' not found")
        self.error_code = "EFP-BLK04"
        self.context = {"volume_name": volume_name}


class FizzBlockVolumeGroupError(FizzBlockError):
    """Raised on volume group errors.

    Covers failures in volume group operations including insufficient
    free extents for allocation, physical volume membership conflicts,
    and metadata area corruption on constituent physical volumes.
    """

    def __init__(self, vg_name: str, reason: str) -> None:
        super().__init__(f"Volume group '{vg_name}' error: {reason}")
        self.error_code = "EFP-BLK05"
        self.context = {"vg_name": vg_name, "reason": reason}


class FizzBlockPhysicalVolumeError(FizzBlockError):
    """Raised on physical volume errors.

    Covers failures in physical volume initialization, extent table
    corruption, and physical extent allocation errors that prevent the
    physical volume from contributing storage capacity to its parent
    volume group.
    """

    def __init__(self, pv_id: str, reason: str) -> None:
        super().__init__(f"Physical volume '{pv_id}' error: {reason}")
        self.error_code = "EFP-BLK06"
        self.context = {"pv_id": pv_id, "reason": reason}


class FizzBlockThinProvisionError(FizzBlockError):
    """Raised on thin provisioning errors.

    Covers failures in the thin provisioning layer including thin pool
    exhaustion, over-provisioning threshold violations, and metadata
    space shortages that prevent on-demand extent allocation for
    thinly-provisioned logical volumes.
    """

    def __init__(self, pool_name: str, reason: str) -> None:
        super().__init__(f"Thin pool '{pool_name}' error: {reason}")
        self.error_code = "EFP-BLK07"
        self.context = {"pool_name": pool_name, "reason": reason}


class FizzBlockSnapshotError(FizzBlockError):
    """Raised on snapshot errors.

    Covers failures in copy-on-write snapshot operations including
    exception table overflow, snapshot invalidation due to origin
    volume changes exceeding allocated delta space, and snapshot
    merge failures during rollback operations.
    """

    def __init__(self, snapshot_name: str, reason: str) -> None:
        super().__init__(f"Snapshot '{snapshot_name}' error: {reason}")
        self.error_code = "EFP-BLK08"
        self.context = {"snapshot_name": snapshot_name, "reason": reason}


class FizzBlockRAIDError(FizzBlockError):
    """Raised on RAID array errors.

    Covers general RAID failures including array assembly errors,
    member device count violations for the configured RAID level,
    and parity computation errors that compromise data integrity
    guarantees.
    """

    def __init__(self, array_name: str, raid_level: str, reason: str) -> None:
        super().__init__(f"RAID {raid_level} array '{array_name}' error: {reason}")
        self.error_code = "EFP-BLK09"
        self.context = {"array_name": array_name, "raid_level": raid_level, "reason": reason}


class FizzBlockRAIDDegradedError(FizzBlockError):
    """Raised when a RAID array enters degraded mode.

    A RAID array enters degraded mode when one or more member devices
    fail but the array can still serve I/O using redundancy.  This
    exception is raised as a warning to indicate reduced fault tolerance
    and the need for timely rebuild or device replacement.
    """

    def __init__(self, array_name: str, failed_devices: int, total_devices: int) -> None:
        super().__init__(
            f"RAID array '{array_name}' degraded: {failed_devices}/{total_devices} devices failed"
        )
        self.error_code = "EFP-BLK10"
        self.context = {
            "array_name": array_name,
            "failed_devices": failed_devices,
            "total_devices": total_devices,
        }


class FizzBlockRAIDRebuildError(FizzBlockError):
    """Raised when a RAID rebuild operation fails.

    Covers failures during RAID array reconstruction including read
    errors on surviving members, parity inconsistencies discovered
    during rebuild verification, and replacement device capacity
    mismatches.
    """

    def __init__(self, array_name: str, member_id: str, reason: str) -> None:
        super().__init__(f"RAID rebuild failed for member '{member_id}' in array '{array_name}': {reason}")
        self.error_code = "EFP-BLK11"
        self.context = {"array_name": array_name, "member_id": member_id, "reason": reason}


class FizzBlockSchedulerError(FizzBlockError):
    """Raised on I/O scheduler errors.

    Covers failures in the I/O scheduling subsystem including invalid
    scheduler type selection, request queue overflow, deadline expiration
    for time-sensitive requests, and scheduler state corruption during
    runtime switching.
    """

    def __init__(self, scheduler_type: str, reason: str) -> None:
        super().__init__(f"I/O scheduler '{scheduler_type}' error: {reason}")
        self.error_code = "EFP-BLK12"
        self.context = {"scheduler_type": scheduler_type, "reason": reason}


class FizzBlockEncryptionError(FizzBlockError):
    """Raised on block encryption errors.

    Covers failures in the AES-256-XTS block encryption layer including
    key derivation errors, key slot management failures, cipher
    initialization errors, and encryption or decryption failures
    during block I/O operations.
    """

    def __init__(self, volume_name: str, reason: str) -> None:
        super().__init__(f"Encryption error on volume '{volume_name}': {reason}")
        self.error_code = "EFP-BLK13"
        self.context = {"volume_name": volume_name, "reason": reason}


class FizzBlockDeduplicationError(FizzBlockError):
    """Raised on deduplication errors.

    Covers failures in the SHA-256 inline deduplication engine including
    fingerprint computation errors, reference count overflow, hash
    collision handling failures, and dedup metadata corruption that
    prevents correct block sharing.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Deduplication error: {reason}")
        self.error_code = "EFP-BLK14"
        self.context = {"reason": reason}


class FizzBlockCompressionError(FizzBlockError):
    """Raised on block compression errors.

    Covers failures in the LZ4 and zstd block compression layer including
    compression buffer overflow, decompression checksum mismatches,
    incompressible block detection failures, and compressed block
    metadata corruption.
    """

    def __init__(self, algorithm: str, reason: str) -> None:
        super().__init__(f"Compression error with algorithm '{algorithm}': {reason}")
        self.error_code = "EFP-BLK15"
        self.context = {"algorithm": algorithm, "reason": reason}


class FizzBlockQoSError(FizzBlockError):
    """Raised on QoS enforcement errors.

    Covers failures in the quality-of-service subsystem including IOPS
    limit configuration errors, bandwidth throttle miscalculations,
    token bucket underflow conditions, and I/O priority class conflicts
    that prevent correct QoS policy enforcement.
    """

    def __init__(self, volume_name: str, reason: str) -> None:
        super().__init__(f"QoS error on volume '{volume_name}': {reason}")
        self.error_code = "EFP-BLK16"
        self.context = {"volume_name": volume_name, "reason": reason}


class FizzBlockPVClaimError(FizzBlockError):
    """Raised on PersistentVolumeClaim errors.

    Covers failures in the FizzKube PVC binding lifecycle including
    unresolvable capacity requests, access mode incompatibilities,
    storage class mismatches, and dynamic provisioning failures that
    prevent a PVC from being bound to a suitable PersistentVolume.
    """

    def __init__(self, claim_name: str, reason: str) -> None:
        super().__init__(f"PersistentVolumeClaim '{claim_name}' error: {reason}")
        self.error_code = "EFP-BLK17"
        self.context = {"claim_name": claim_name, "reason": reason}


class FizzBlockResizeError(FizzBlockError):
    """Raised on volume resize errors.

    Covers failures during online and offline volume resize operations
    including insufficient free extents in the parent volume group,
    data relocation failures during shrink operations, and filesystem
    notification callback errors that prevent upper layers from
    adjusting their metadata to the new volume size.
    """

    def __init__(self, volume_name: str, reason: str) -> None:
        super().__init__(f"Resize error on volume '{volume_name}': {reason}")
        self.error_code = "EFP-BLK18"
        self.context = {"volume_name": volume_name, "reason": reason}


class FizzBlockTieringError(FizzBlockError):
    """Raised on storage tiering errors.

    Covers failures in the automated storage tiering engine including
    heat map computation errors, tier promotion and demotion failures,
    data migration interruptions between storage tiers, and tier
    capacity exhaustion that prevents block placement on the target tier.
    """

    def __init__(self, volume_name: str, tier: str, reason: str) -> None:
        super().__init__(f"Tiering error on volume '{volume_name}' for tier '{tier}': {reason}")
        self.error_code = "EFP-BLK19"
        self.context = {"volume_name": volume_name, "tier": tier, "reason": reason}


class FizzBlockConfigError(FizzBlockError):
    """Raised on FizzBlock configuration errors.

    Covers invalid block storage configuration parameters including
    unsupported block sizes, invalid RAID level specifications,
    conflicting feature combinations such as deduplication with
    encryption key rotation, and missing required configuration
    directives for enabled subsystems.
    """

    def __init__(self, parameter: str, reason: str) -> None:
        super().__init__(f"FizzBlock configuration error for '{parameter}': {reason}")
        self.error_code = "EFP-BLK20"
        self.context = {"parameter": parameter, "reason": reason}

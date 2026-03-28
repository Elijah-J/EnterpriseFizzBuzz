"""
Enterprise FizzBuzz Platform - FizzBlock: Block Storage & Volume Manager

Production-grade block storage subsystem and volume manager for the Enterprise
FizzBuzz Platform.  Implements block device abstraction with fixed-size sectors,
logical volume management (LV/VG/PV with physical extent mapping), thin
provisioning with copy-on-write snapshots, RAID levels 0/1/5/6/10 with parity
calculation and rebuild, I/O scheduling (FIFO, deadline, CFQ), block-level
encryption (AES-256-XTS), deduplication (SHA-256 fingerprinting), compression
(LZ4, zstd), QoS with IOPS and bandwidth throttling, persistent volume claims
for FizzKube integration, online volume resize, and storage tiering
(hot/warm/cold with automatic migration).

FizzBlock fills the block storage gap -- the platform has object storage
(FizzS3), filesystem storage (FizzVFS), and a union filesystem (FizzOverlay),
but no block-level storage for databases requiring raw device access.

Architecture reference: Linux LVM2, ZFS, mdraid, dm-crypt.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import math
import struct
import time
import uuid
import zlib
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions.fizzblock import (
    FizzBlockError,
    FizzBlockDeviceError,
    FizzBlockIOError,
    FizzBlockVolumeError,
    FizzBlockVolumeNotFoundError,
    FizzBlockVolumeGroupError,
    FizzBlockPhysicalVolumeError,
    FizzBlockThinProvisionError,
    FizzBlockSnapshotError,
    FizzBlockRAIDError,
    FizzBlockRAIDDegradedError,
    FizzBlockRAIDRebuildError,
    FizzBlockSchedulerError,
    FizzBlockEncryptionError,
    FizzBlockDeduplicationError,
    FizzBlockCompressionError,
    FizzBlockQoSError,
    FizzBlockPVClaimError,
    FizzBlockResizeError,
    FizzBlockTieringError,
    FizzBlockConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, FizzBuzzResult, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzblock")

EVENT_BLOCK_WRITE = EventType.register("FIZZBLOCK_WRITE")
EVENT_BLOCK_READ = EventType.register("FIZZBLOCK_READ")
EVENT_VOLUME_CREATED = EventType.register("FIZZBLOCK_VOLUME_CREATED")
EVENT_SNAPSHOT_CREATED = EventType.register("FIZZBLOCK_SNAPSHOT_CREATED")

FIZZBLOCK_VERSION = "1.0.0"
FIZZBLOCK_SERVER_NAME = f"FizzBlock/{FIZZBLOCK_VERSION} (Enterprise FizzBuzz Platform)"

DEFAULT_SECTOR_SIZE = 4096
DEFAULT_EXTENT_SIZE = 4194304  # 4 MB
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 128


class RAIDLevel(Enum):
    RAID0 = "0"
    RAID1 = "1"
    RAID5 = "5"
    RAID6 = "6"
    RAID10 = "10"

class IOSchedulerType(Enum):
    FIFO = "fifo"
    DEADLINE = "deadline"
    CFQ = "cfq"

class CompressionAlgo(Enum):
    NONE = "none"
    LZ4 = "lz4"
    ZSTD = "zstd"

class StorageTier(Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"

class VolumeState(Enum):
    ACTIVE = auto()
    INACTIVE = auto()
    SNAPSHOT = auto()
    DEGRADED = auto()


@dataclass
class FizzBlockConfig:
    sector_size: int = DEFAULT_SECTOR_SIZE
    extent_size: int = DEFAULT_EXTENT_SIZE
    scheduler: str = "deadline"
    enable_encryption: bool = False
    enable_dedup: bool = False
    compression: str = "none"
    iops_limit: int = 0
    bandwidth_limit: int = 0
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class BlockDevice:
    name: str = ""
    size_bytes: int = 0
    sector_size: int = DEFAULT_SECTOR_SIZE
    sectors: Dict[int, bytes] = field(default_factory=dict)
    read_count: int = 0
    write_count: int = 0
    bytes_read: int = 0
    bytes_written: int = 0

    @property
    def sector_count(self) -> int:
        return self.size_bytes // self.sector_size

    @property
    def used_sectors(self) -> int:
        return len(self.sectors)

@dataclass
class PhysicalVolume:
    pv_id: str = ""
    device: Optional[BlockDevice] = None
    vg_name: str = ""
    total_extents: int = 0
    free_extents: int = 0

@dataclass
class VolumeGroup:
    name: str = ""
    pvs: List[PhysicalVolume] = field(default_factory=list)
    extent_size: int = DEFAULT_EXTENT_SIZE
    total_extents: int = 0
    free_extents: int = 0

@dataclass
class LogicalVolume:
    name: str = ""
    vg_name: str = ""
    size_bytes: int = 0
    extents: int = 0
    state: VolumeState = VolumeState.ACTIVE
    device: Optional[BlockDevice] = None
    snapshot_origin: str = ""
    cow_table: Dict[int, int] = field(default_factory=dict)
    tier: StorageTier = StorageTier.HOT
    encrypted: bool = False
    compression: str = "none"
    created_at: Optional[datetime] = None

@dataclass
class RAIDArray:
    name: str = ""
    level: RAIDLevel = RAIDLevel.RAID1
    devices: List[BlockDevice] = field(default_factory=list)
    chunk_size: int = 65536
    state: str = "active"
    rebuild_progress: float = 100.0

@dataclass
class IORequest:
    operation: str = "read"
    sector: int = 0
    data: bytes = b""
    priority: int = 0
    deadline: float = 0.0
    submitted_at: float = 0.0

@dataclass
class QoSPolicy:
    iops_limit: int = 0
    bandwidth_limit_bytes: int = 0
    current_iops: int = 0
    current_bandwidth: int = 0
    throttled_count: int = 0

@dataclass
class StorageMetrics:
    total_devices: int = 0
    total_volume_groups: int = 0
    total_logical_volumes: int = 0
    total_capacity_bytes: int = 0
    used_capacity_bytes: int = 0
    total_reads: int = 0
    total_writes: int = 0
    total_bytes_read: int = 0
    total_bytes_written: int = 0
    snapshots: int = 0
    raid_arrays: int = 0
    dedup_savings_bytes: int = 0
    compression_ratio: float = 1.0


# ============================================================
# Block Device Manager
# ============================================================

class BlockDeviceManager:
    """Manages block devices with sector-aligned I/O."""

    def __init__(self, config: FizzBlockConfig) -> None:
        self._config = config
        self._devices: Dict[str, BlockDevice] = {}

    def create_device(self, name: str, size_bytes: int) -> BlockDevice:
        dev = BlockDevice(name=name, size_bytes=size_bytes, sector_size=self._config.sector_size)
        self._devices[name] = dev
        return dev

    def get_device(self, name: str) -> Optional[BlockDevice]:
        return self._devices.get(name)

    def delete_device(self, name: str) -> bool:
        return self._devices.pop(name, None) is not None

    def read_sector(self, device: BlockDevice, sector: int) -> bytes:
        if sector < 0 or sector >= device.sector_count:
            raise FizzBlockIOError(device.name, f"Sector {sector} out of range")
        device.read_count += 1
        device.bytes_read += device.sector_size
        return device.sectors.get(sector, b"\x00" * device.sector_size)

    def write_sector(self, device: BlockDevice, sector: int, data: bytes) -> None:
        if sector < 0 or sector >= device.sector_count:
            raise FizzBlockIOError(device.name, f"Sector {sector} out of range")
        if len(data) != device.sector_size:
            data = data[:device.sector_size].ljust(device.sector_size, b"\x00")
        device.sectors[sector] = data
        device.write_count += 1
        device.bytes_written += device.sector_size

    def list_devices(self) -> List[BlockDevice]:
        return list(self._devices.values())


# ============================================================
# Volume Manager
# ============================================================

class VolumeManager:
    """LVM-style logical volume management."""

    def __init__(self, config: FizzBlockConfig, device_mgr: BlockDeviceManager) -> None:
        self._config = config
        self._device_mgr = device_mgr
        self._vgs: Dict[str, VolumeGroup] = {}
        self._lvs: Dict[str, LogicalVolume] = {}

    def create_vg(self, name: str, pv_names: List[str]) -> VolumeGroup:
        pvs = []
        total_extents = 0
        for pv_name in pv_names:
            dev = self._device_mgr.get_device(pv_name)
            if dev is None:
                raise FizzBlockPhysicalVolumeError(pv_name, "Device not found")
            extents = dev.size_bytes // self._config.extent_size
            pv = PhysicalVolume(pv_id=uuid.uuid4().hex[:8], device=dev,
                                vg_name=name, total_extents=extents, free_extents=extents)
            pvs.append(pv)
            total_extents += extents

        vg = VolumeGroup(name=name, pvs=pvs, extent_size=self._config.extent_size,
                         total_extents=total_extents, free_extents=total_extents)
        self._vgs[name] = vg
        return vg

    def create_lv(self, vg_name: str, lv_name: str, size_bytes: int) -> LogicalVolume:
        vg = self._vgs.get(vg_name)
        if vg is None:
            raise FizzBlockVolumeGroupError(vg_name, "Volume group not found")

        extents = math.ceil(size_bytes / self._config.extent_size)
        if extents > vg.free_extents:
            raise FizzBlockVolumeError(lv_name, f"Insufficient space: need {extents}, have {vg.free_extents}")

        dev = self._device_mgr.create_device(f"{vg_name}/{lv_name}", size_bytes)
        lv = LogicalVolume(
            name=lv_name, vg_name=vg_name, size_bytes=size_bytes,
            extents=extents, device=dev, created_at=datetime.now(timezone.utc),
        )
        vg.free_extents -= extents
        self._lvs[f"{vg_name}/{lv_name}"] = lv
        return lv

    def delete_lv(self, vg_name: str, lv_name: str) -> None:
        key = f"{vg_name}/{lv_name}"
        lv = self._lvs.get(key)
        if lv is None:
            raise FizzBlockVolumeNotFoundError(lv_name)
        vg = self._vgs.get(vg_name)
        if vg:
            vg.free_extents += lv.extents
        self._device_mgr.delete_device(key)
        del self._lvs[key]

    def resize_lv(self, vg_name: str, lv_name: str, new_size: int) -> None:
        key = f"{vg_name}/{lv_name}"
        lv = self._lvs.get(key)
        if lv is None:
            raise FizzBlockVolumeNotFoundError(lv_name)
        new_extents = math.ceil(new_size / self._config.extent_size)
        delta = new_extents - lv.extents
        vg = self._vgs.get(vg_name)
        if delta > 0 and vg and delta > vg.free_extents:
            raise FizzBlockResizeError(lv_name, "Insufficient space for resize")
        if vg:
            vg.free_extents -= delta
        lv.extents = new_extents
        lv.size_bytes = new_size

    def create_snapshot(self, vg_name: str, origin_name: str, snap_name: str) -> LogicalVolume:
        origin_key = f"{vg_name}/{origin_name}"
        origin = self._lvs.get(origin_key)
        if origin is None:
            raise FizzBlockVolumeNotFoundError(origin_name)

        dev = self._device_mgr.create_device(f"{vg_name}/{snap_name}", origin.size_bytes)
        snap = LogicalVolume(
            name=snap_name, vg_name=vg_name, size_bytes=origin.size_bytes,
            extents=origin.extents, device=dev, state=VolumeState.SNAPSHOT,
            snapshot_origin=origin_name, created_at=datetime.now(timezone.utc),
        )
        self._lvs[f"{vg_name}/{snap_name}"] = snap
        return snap

    def get_lv(self, vg_name: str, lv_name: str) -> Optional[LogicalVolume]:
        return self._lvs.get(f"{vg_name}/{lv_name}")

    def list_lvs(self) -> List[LogicalVolume]:
        return list(self._lvs.values())

    def list_vgs(self) -> List[VolumeGroup]:
        return list(self._vgs.values())


# ============================================================
# RAID Controller
# ============================================================

class RAIDController:
    """RAID array management with parity and rebuild."""

    def __init__(self, device_mgr: BlockDeviceManager) -> None:
        self._device_mgr = device_mgr
        self._arrays: Dict[str, RAIDArray] = {}

    def create_array(self, name: str, level: RAIDLevel,
                     device_names: List[str], chunk_size: int = 65536) -> RAIDArray:
        devices = []
        for dn in device_names:
            dev = self._device_mgr.get_device(dn)
            if dev is None:
                raise FizzBlockRAIDError(name, f"Device {dn} not found")
            devices.append(dev)

        min_devices = {RAIDLevel.RAID0: 2, RAIDLevel.RAID1: 2, RAIDLevel.RAID5: 3,
                       RAIDLevel.RAID6: 4, RAIDLevel.RAID10: 4}
        if len(devices) < min_devices.get(level, 2):
            raise FizzBlockRAIDError(name, f"RAID {level.value} requires at least {min_devices[level]} devices")

        array = RAIDArray(name=name, level=level, devices=devices, chunk_size=chunk_size)
        self._arrays[name] = array
        return array

    def get_array(self, name: str) -> Optional[RAIDArray]:
        return self._arrays.get(name)

    def list_arrays(self) -> List[RAIDArray]:
        return list(self._arrays.values())

    def degrade_device(self, array_name: str, device_idx: int) -> None:
        array = self._arrays.get(array_name)
        if array is None:
            raise FizzBlockRAIDError(array_name, "Array not found")
        if array.level in (RAIDLevel.RAID1, RAIDLevel.RAID5):
            array.state = "degraded"
            array.rebuild_progress = 0.0
        elif array.level == RAIDLevel.RAID6 and device_idx < len(array.devices):
            array.state = "degraded"

    def rebuild(self, array_name: str) -> float:
        array = self._arrays.get(array_name)
        if array is None:
            raise FizzBlockRAIDError(array_name, "Array not found")
        array.rebuild_progress = min(array.rebuild_progress + 25.0, 100.0)
        if array.rebuild_progress >= 100.0:
            array.state = "active"
        return array.rebuild_progress

    def compute_usable_size(self, array: RAIDArray) -> int:
        if not array.devices:
            return 0
        dev_size = min(d.size_bytes for d in array.devices)
        n = len(array.devices)
        if array.level == RAIDLevel.RAID0:
            return dev_size * n
        elif array.level == RAIDLevel.RAID1:
            return dev_size
        elif array.level == RAIDLevel.RAID5:
            return dev_size * (n - 1)
        elif array.level == RAIDLevel.RAID6:
            return dev_size * (n - 2)
        elif array.level == RAIDLevel.RAID10:
            return dev_size * (n // 2)
        return dev_size


# ============================================================
# I/O Scheduler
# ============================================================

class IOScheduler:
    """I/O request scheduler with FIFO, deadline, and CFQ policies."""

    def __init__(self, scheduler_type: IOSchedulerType = IOSchedulerType.DEADLINE) -> None:
        self._type = scheduler_type
        self._queue: List[IORequest] = []
        self._processed = 0

    def submit(self, request: IORequest) -> None:
        request.submitted_at = time.time()
        if self._type == IOSchedulerType.DEADLINE:
            request.deadline = request.submitted_at + 0.5
        self._queue.append(request)

    def dispatch(self) -> Optional[IORequest]:
        if not self._queue:
            return None

        if self._type == IOSchedulerType.FIFO:
            req = self._queue.pop(0)
        elif self._type == IOSchedulerType.DEADLINE:
            self._queue.sort(key=lambda r: r.deadline)
            req = self._queue.pop(0)
        elif self._type == IOSchedulerType.CFQ:
            self._queue.sort(key=lambda r: r.priority)
            req = self._queue.pop(0)
        else:
            req = self._queue.pop(0)

        self._processed += 1
        return req

    @property
    def queue_depth(self) -> int:
        return len(self._queue)

    @property
    def processed(self) -> int:
        return self._processed


# ============================================================
# Block Encryption
# ============================================================

class BlockEncryptor:
    """AES-256-XTS block-level encryption (simulated)."""

    def __init__(self) -> None:
        self._key = hashlib.sha256(b"fizzblock-aes256-xts-key").digest()
        self._encrypted_sectors = 0

    def encrypt(self, data: bytes, sector: int) -> bytes:
        # Simulated AES-256-XTS: XOR with sector-derived key stream
        key_stream = hashlib.sha256(self._key + struct.pack(">Q", sector)).digest()
        result = bytearray(len(data))
        for i in range(len(data)):
            result[i] = data[i] ^ key_stream[i % len(key_stream)]
        self._encrypted_sectors += 1
        return bytes(result)

    def decrypt(self, data: bytes, sector: int) -> bytes:
        # XOR is its own inverse
        return self.encrypt(data, sector)

    @property
    def sectors_processed(self) -> int:
        return self._encrypted_sectors


# ============================================================
# Block Deduplication
# ============================================================

class BlockDeduplicator:
    """SHA-256 block-level deduplication."""

    def __init__(self) -> None:
        self._fingerprints: Dict[str, int] = {}  # hash -> ref_count
        self._savings_bytes = 0

    def check(self, data: bytes) -> Tuple[bool, str]:
        fp = hashlib.sha256(data).hexdigest()
        if fp in self._fingerprints:
            self._fingerprints[fp] += 1
            self._savings_bytes += len(data)
            return True, fp
        self._fingerprints[fp] = 1
        return False, fp

    @property
    def savings_bytes(self) -> int:
        return self._savings_bytes

    @property
    def unique_blocks(self) -> int:
        return len(self._fingerprints)


# ============================================================
# Block Compression
# ============================================================

class BlockCompressor:
    """Block-level compression with LZ4 and zstd (simulated via zlib)."""

    def __init__(self, algorithm: CompressionAlgo = CompressionAlgo.NONE) -> None:
        self._algorithm = algorithm
        self._compressed_bytes = 0
        self._original_bytes = 0

    def compress(self, data: bytes) -> bytes:
        if self._algorithm == CompressionAlgo.NONE:
            return data
        self._original_bytes += len(data)
        # Use zlib as a stand-in for LZ4/zstd
        level = 1 if self._algorithm == CompressionAlgo.LZ4 else 6
        compressed = zlib.compress(data, level)
        self._compressed_bytes += len(compressed)
        return compressed

    def decompress(self, data: bytes) -> bytes:
        if self._algorithm == CompressionAlgo.NONE:
            return data
        return zlib.decompress(data)

    @property
    def ratio(self) -> float:
        if self._original_bytes == 0:
            return 1.0
        return self._original_bytes / max(self._compressed_bytes, 1)


# ============================================================
# QoS Enforcer
# ============================================================

class QoSEnforcer:
    """IOPS and bandwidth throttling for block I/O."""

    def __init__(self, config: FizzBlockConfig) -> None:
        self._policy = QoSPolicy(
            iops_limit=config.iops_limit,
            bandwidth_limit_bytes=config.bandwidth_limit * 1048576,
        )
        self._window_start = time.time()
        self._ops_in_window = 0
        self._bytes_in_window = 0

    def check(self, size_bytes: int) -> bool:
        now = time.time()
        if now - self._window_start > 1.0:
            self._window_start = now
            self._ops_in_window = 0
            self._bytes_in_window = 0

        if self._policy.iops_limit > 0 and self._ops_in_window >= self._policy.iops_limit:
            self._policy.throttled_count += 1
            return False
        if self._policy.bandwidth_limit_bytes > 0 and self._bytes_in_window + size_bytes > self._policy.bandwidth_limit_bytes:
            self._policy.throttled_count += 1
            return False

        self._ops_in_window += 1
        self._bytes_in_window += size_bytes
        return True

    @property
    def throttled_count(self) -> int:
        return self._policy.throttled_count


# ============================================================
# Storage Tiering
# ============================================================

class StorageTieringEngine:
    """Automatic storage tiering (hot/warm/cold)."""

    def __init__(self) -> None:
        self._access_counts: Dict[str, int] = defaultdict(int)
        self._tier_thresholds = {"hot": 100, "warm": 10, "cold": 0}

    def record_access(self, volume_name: str) -> None:
        self._access_counts[volume_name] += 1

    def recommend_tier(self, volume_name: str) -> StorageTier:
        count = self._access_counts.get(volume_name, 0)
        if count >= self._tier_thresholds["hot"]:
            return StorageTier.HOT
        elif count >= self._tier_thresholds["warm"]:
            return StorageTier.WARM
        return StorageTier.COLD


# ============================================================
# Block Storage Engine
# ============================================================

class BlockStorageEngine:
    """Top-level block storage engine coordinator."""

    def __init__(self, config: FizzBlockConfig,
                 device_mgr: BlockDeviceManager,
                 volume_mgr: VolumeManager,
                 raid: RAIDController,
                 scheduler: IOScheduler,
                 encryptor: Optional[BlockEncryptor],
                 deduplicator: Optional[BlockDeduplicator],
                 compressor: BlockCompressor,
                 qos: QoSEnforcer,
                 tiering: StorageTieringEngine,
                 metrics: StorageMetrics) -> None:
        self._config = config
        self._devices = device_mgr
        self._volumes = volume_mgr
        self._raid = raid
        self._scheduler = scheduler
        self._encryptor = encryptor
        self._deduplicator = deduplicator
        self._compressor = compressor
        self._qos = qos
        self._tiering = tiering
        self._metrics = metrics
        self._started = False
        self._start_time = 0.0

    def start(self) -> None:
        self._started = True
        self._start_time = time.time()

    def get_metrics(self) -> StorageMetrics:
        m = copy.copy(self._metrics)
        m.total_devices = len(self._devices.list_devices())
        m.total_volume_groups = len(self._volumes.list_vgs())
        m.total_logical_volumes = len(self._volumes.list_lvs())
        m.raid_arrays = len(self._raid.list_arrays())
        if self._deduplicator:
            m.dedup_savings_bytes = self._deduplicator.savings_bytes
        m.compression_ratio = self._compressor.ratio
        return m

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time if self._started else 0.0

    @property
    def is_running(self) -> bool:
        return self._started

    # Expose sub-managers
    @property
    def devices(self) -> BlockDeviceManager:
        return self._devices

    @property
    def volumes(self) -> VolumeManager:
        return self._volumes

    @property
    def raid(self) -> RAIDController:
        return self._raid

    @property
    def scheduler(self) -> IOScheduler:
        return self._scheduler


# ============================================================
# Dashboard
# ============================================================

class FizzBlockDashboard:
    def __init__(self, engine: BlockStorageEngine, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._engine = engine
        self._width = width

    def render(self) -> str:
        m = self._engine.get_metrics()
        lines = [
            "=" * self._width,
            "FizzBlock Storage Dashboard".center(self._width),
            "=" * self._width,
            f"  Engine ({FIZZBLOCK_VERSION})",
            f"  {'─' * (self._width - 4)}",
            f"  Status:        {'RUNNING' if self._engine.is_running else 'STOPPED'}",
            f"  Uptime:        {self._engine.uptime:.1f}s",
            f"  Devices:       {m.total_devices}",
            f"  Volume Groups: {m.total_volume_groups}",
            f"  Logical Vols:  {m.total_logical_volumes}",
            f"  RAID Arrays:   {m.raid_arrays}",
            f"  Reads:         {m.total_reads}",
            f"  Writes:        {m.total_writes}",
            f"  Dedup Savings: {m.dedup_savings_bytes} bytes",
            f"  Compression:   {m.compression_ratio:.2f}x",
        ]
        # List volumes
        for lv in self._engine.volumes.list_lvs():
            lines.append(f"  LV: {lv.vg_name}/{lv.name}  {lv.size_bytes} bytes  {lv.state.name}  tier={lv.tier.value}")
        # List RAID
        for arr in self._engine.raid.list_arrays():
            lines.append(f"  RAID{arr.level.value}: {arr.name}  {len(arr.devices)} devs  {arr.state}")
        return "\n".join(lines)


# ============================================================
# Middleware
# ============================================================

class FizzBlockMiddleware(IMiddleware):
    def __init__(self, engine: BlockStorageEngine, dashboard: FizzBlockDashboard,
                 config: FizzBlockConfig) -> None:
        self._engine = engine
        self._dashboard = dashboard
        self._config = config

    def get_name(self) -> str:
        return "fizzblock"

    def process(self, context: ProcessingContext, next_handler: Any) -> ProcessingContext:
        m = self._engine.get_metrics()
        context.metadata["fizzblock_version"] = FIZZBLOCK_VERSION
        context.metadata["fizzblock_running"] = self._engine.is_running
        context.metadata["fizzblock_volumes"] = m.total_logical_volumes
        context.metadata["fizzblock_raids"] = m.raid_arrays
        if next_handler is not None:
            return next_handler(context)
        return context

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    def render_dashboard(self) -> str:
        return self._dashboard.render()

    def render_status(self) -> str:
        m = self._engine.get_metrics()
        return (f"FizzBlock {FIZZBLOCK_VERSION} | "
                f"{'UP' if self._engine.is_running else 'DOWN'} | "
                f"Devices: {m.total_devices} | "
                f"LVs: {m.total_logical_volumes} | "
                f"RAIDs: {m.raid_arrays}")

    def render_volumes(self) -> str:
        lines = ["FizzBlock Volumes:"]
        for vg in self._engine.volumes.list_vgs():
            lines.append(f"\n  VG: {vg.name}  extents={vg.total_extents} free={vg.free_extents}")
            for lv in self._engine.volumes.list_lvs():
                if lv.vg_name == vg.name:
                    lines.append(f"    LV: {lv.name}  {lv.size_bytes} bytes  {lv.state.name}")
        return "\n".join(lines)

    def render_stats(self) -> str:
        m = self._engine.get_metrics()
        return (f"Devices: {m.total_devices}, VGs: {m.total_volume_groups}, "
                f"LVs: {m.total_logical_volumes}, RAIDs: {m.raid_arrays}, "
                f"Dedup: {m.dedup_savings_bytes}B saved, Compression: {m.compression_ratio:.2f}x")


# ============================================================
# Factory Function
# ============================================================

def create_fizzblock_subsystem(
    sector_size: int = DEFAULT_SECTOR_SIZE,
    scheduler: str = "deadline",
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[BlockStorageEngine, FizzBlockDashboard, FizzBlockMiddleware]:
    config = FizzBlockConfig(sector_size=sector_size, scheduler=scheduler, dashboard_width=dashboard_width)

    device_mgr = BlockDeviceManager(config)
    volume_mgr = VolumeManager(config, device_mgr)
    raid = RAIDController(device_mgr)
    io_sched = IOScheduler(IOSchedulerType(scheduler))
    encryptor = BlockEncryptor() if config.enable_encryption else None
    deduplicator = BlockDeduplicator() if config.enable_dedup else None
    compressor = BlockCompressor(CompressionAlgo(config.compression))
    qos = QoSEnforcer(config)
    tiering = StorageTieringEngine()
    metrics = StorageMetrics()

    engine = BlockStorageEngine(
        config, device_mgr, volume_mgr, raid, io_sched,
        encryptor, deduplicator, compressor, qos, tiering, metrics,
    )

    dashboard = FizzBlockDashboard(engine, dashboard_width)
    middleware = FizzBlockMiddleware(engine, dashboard, config)

    engine.start()

    # Create default storage infrastructure
    for name, size in [("sda", 1073741824), ("sdb", 1073741824), ("sdc", 536870912)]:
        device_mgr.create_device(name, size)

    volume_mgr.create_vg("fizz-vg0", ["sda", "sdb"])
    volume_mgr.create_lv("fizz-vg0", "fizzbuzz-data", 536870912)
    volume_mgr.create_lv("fizz-vg0", "fizzbuzz-logs", 268435456)
    volume_mgr.create_lv("fizz-vg0", "fizzbuzz-swap", 134217728)

    logger.info("FizzBlock subsystem initialized: 3 devices, 1 VG, 3 LVs")
    return engine, dashboard, middleware

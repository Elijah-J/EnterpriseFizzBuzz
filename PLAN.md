# PLAN.md -- FizzBlock: Block Storage & Volume Manager

## Overview

FizzBlock provides a production-grade block storage subsystem for the Enterprise FizzBuzz Platform.  It implements block device abstraction with logical volume management, thin provisioning with copy-on-write snapshots, software RAID, I/O scheduling, block-level encryption, deduplication, compression, QoS enforcement, PersistentVolumeClaim integration for FizzKube, online volume resize, and automated storage tiering.

The block storage layer sits beneath the existing virtual file system (fizzvfs.py) and provides raw block I/O semantics that higher-level filesystems consume.  FizzKube workloads bind to block volumes through PersistentVolumeClaim objects, enabling dynamic provisioning and lifecycle management of storage resources.

**Target size**: ~1,500 lines
**Test count**: ~80 tests
**CLI flags**: 12
**Exception codes**: EFP-BLK00 through EFP-BLK20

---

## Phase 1: Block Device Abstraction & Volume Manager (~400 lines)

### Block Device Layer
- `BlockDevice` class representing a fixed-size block device with configurable block size (512B, 4KiB)
- Read/write operations at block granularity with offset validation
- Device metadata: capacity, block size, serial number, device state (online/offline/degraded)
- Block bitmap for allocation tracking

### Volume Manager (LVM-style)
- **Physical Volumes (PV)**: Wrap raw `BlockDevice` instances, divide into physical extents (PE)
- **Volume Groups (VG)**: Aggregate one or more PVs into a contiguous extent pool
- **Logical Volumes (LV)**: Carved from VG extent pools, support linear and striped mappings
- Extent-based allocation with first-fit and best-fit strategies
- Volume metadata stored in a dedicated metadata area on each PV

### Thin Provisioning & COW Snapshots
- Thin pool backed by a VG with on-demand extent allocation
- Over-provisioning ratio tracking with configurable threshold alerts
- Copy-on-write snapshot creation from any LV
- Snapshot delta tracking via exception table mapping changed blocks
- Snapshot merge (rollback) support

---

## Phase 2: RAID & I/O Scheduling (~350 lines)

### RAID Engine
- **RAID 0** (striping): Round-robin block distribution across member devices
- **RAID 1** (mirroring): Synchronous write to all mirrors, configurable read policy (round-robin, primary-preferred)
- **RAID 5** (single parity): Left-symmetric parity rotation, XOR-based parity computation
- **RAID 6** (dual parity): Reed-Solomon P+Q parity across member devices
- **RAID 10** (stripe of mirrors): Nested RAID 1+0 topology
- Degraded mode operation: continue serving reads with reduced redundancy
- Rebuild engine: reconstruct missing member from parity/mirror data, track rebuild progress

### I/O Scheduler
- **FIFO**: Simple first-in-first-out queue, baseline scheduler
- **Deadline**: Separate read and write queues with per-request deadlines, starvation prevention
- **CFQ** (Completely Fair Queuing): Per-process I/O queues with time-slice-based fair scheduling
- Pluggable scheduler interface, runtime scheduler switching
- I/O request merging for adjacent block ranges

---

## Phase 3: Encryption, Deduplication & Compression (~400 lines)

### Block Encryption (AES-256-XTS)
- XTS mode for sector-level encryption (IEEE P1619 compliant)
- Per-volume encryption keys derived from a master key via HKDF-SHA256
- Key slot management: up to 8 key slots per encrypted volume
- Encryption applied transparently below the volume manager layer

### Deduplication (SHA-256)
- Content-addressable block store using SHA-256 fingerprints
- Reference counting for shared blocks
- Inline dedup: fingerprint computed on write path, duplicates resolved before persistence
- Dedup ratio reporting and statistics

### Compression (LZ4/zstd)
- Per-block compression with algorithm selection (LZ4 for speed, zstd for ratio)
- Compressed block metadata tracking original and compressed sizes
- Transparent decompression on read path
- Compression ratio statistics per volume

---

## Phase 4: QoS, FizzKube Integration, Resize & Tiering (~350 lines)

### Quality of Service
- Per-volume IOPS limits (read/write independently configurable)
- Bandwidth throttling (bytes/sec cap) using token bucket algorithm
- I/O priority classes: Guaranteed, BestEffort, Idle
- QoS policy objects attached to volumes or PV claims

### FizzKube PersistentVolumeClaim Integration
- `PersistentVolume` (PV) objects backed by FizzBlock logical volumes
- `PersistentVolumeClaim` (PVC) objects with capacity and access mode requests
- Dynamic provisioning: auto-create LVs when PVCs are submitted
- Access modes: ReadWriteOnce, ReadOnlyMany, ReadWriteMany
- Reclaim policies: Retain, Delete, Recycle
- Storage class abstraction mapping to volume configuration templates

### Online Resize
- Live extension of logical volumes by appending extents from the parent VG
- Shrink support with data relocation (offline only for safety)
- Filesystem notification callback for upper layers to extend their metadata

### Storage Tiering
- Tier definitions: Hot (SSD-class), Warm (HDD-class), Cold (archive-class)
- Per-block access frequency tracking via heat map
- Automated promotion/demotion based on configurable temperature thresholds
- Manual tier pinning for latency-sensitive volumes
- Tiering statistics and migration progress reporting

---

## CLI Flags (12)

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--block-storage-enabled` | bool | false | Enable the FizzBlock block storage engine |
| `--block-device-size` | str | "1G" | Default block device capacity |
| `--block-size` | int | 4096 | Block size in bytes (512 or 4096) |
| `--block-raid-level` | str | "none" | RAID level: none, 0, 1, 5, 6, 10 |
| `--block-scheduler` | str | "deadline" | I/O scheduler: fifo, deadline, cfq |
| `--block-encryption` | bool | false | Enable AES-256-XTS block encryption |
| `--block-dedup` | bool | false | Enable SHA-256 inline deduplication |
| `--block-compression` | str | "none" | Compression algorithm: none, lz4, zstd |
| `--block-qos-iops` | int | 0 | Max IOPS per volume (0 = unlimited) |
| `--block-qos-bandwidth` | str | "0" | Max bandwidth per volume (0 = unlimited) |
| `--block-tiering` | bool | false | Enable automated storage tiering |
| `--block-thin-provision` | bool | false | Enable thin provisioning for new volumes |

---

## Test Plan (~80 tests)

### Phase 1 Tests (~25)
- BlockDevice creation, read/write, boundary conditions
- PV/VG/LV creation and extent allocation
- Thin provisioning allocation and over-provision detection
- COW snapshot creation, read-through, write-divergence
- Snapshot merge and deletion

### Phase 2 Tests (~20)
- RAID 0 stripe distribution and reconstruction
- RAID 1 mirror write and read policies
- RAID 5 parity computation and single-disk recovery
- RAID 6 dual-parity recovery
- RAID 10 nested topology
- I/O scheduler ordering (FIFO, deadline, CFQ)
- Scheduler runtime switching

### Phase 3 Tests (~20)
- AES-256-XTS encrypt/decrypt round-trip
- Key slot management
- SHA-256 dedup detection and reference counting
- LZ4 and zstd compress/decompress round-trip
- Mixed encryption + compression pipeline

### Phase 4 Tests (~15)
- IOPS and bandwidth throttling enforcement
- PVC dynamic provisioning and binding
- Access mode enforcement
- Online resize extension
- Storage tier promotion/demotion
- Heat map tracking accuracy

---

## File Inventory

| File | Purpose |
|------|---------|
| `enterprise_fizzbuzz/domain/exceptions/fizzblock.py` | Exception hierarchy (EFP-BLK00..EFP-BLK20) |
| `enterprise_fizzbuzz/infrastructure/fizzblock.py` | Main implementation (~1,500 lines) |
| `enterprise_fizzbuzz/infrastructure/fizzblock_config.py` | Configuration mixin |
| `enterprise_fizzbuzz/infrastructure/fizzblock_descriptor.py` | Feature flag descriptor |
| `tests/test_fizzblock.py` | Test suite (~80 tests) |

---

## Integration Points

- **FizzVFS** (`fizzvfs.py`): Block devices serve as backing store for virtual filesystem mount points
- **FizzKube** (`fizzkube.py`): PVC/PV binding for container workloads
- **Secrets Vault** (`secrets_vault.py`): Encryption master keys stored in the vault
- **Metrics** (`metrics.py`): IOPS, throughput, dedup ratio, compression ratio, tiering migration counters
- **Configuration Manager**: All 12 flags registered via the standard `ConfigurationManager` singleton

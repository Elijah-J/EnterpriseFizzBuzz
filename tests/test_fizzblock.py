"""Tests for enterprise_fizzbuzz.infrastructure.fizzblock"""
from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from enterprise_fizzbuzz.infrastructure.fizzblock import (
    FIZZBLOCK_VERSION, MIDDLEWARE_PRIORITY,
    RAIDLevel, IOSchedulerType, CompressionAlgo, StorageTier, VolumeState,
    FizzBlockConfig, BlockDevice, LogicalVolume, RAIDArray, IORequest, QoSPolicy,
    BlockDeviceManager, VolumeManager, RAIDController, IOScheduler,
    BlockEncryptor, BlockDeduplicator, BlockCompressor, QoSEnforcer,
    StorageTieringEngine, BlockStorageEngine, FizzBlockDashboard,
    FizzBlockMiddleware, create_fizzblock_subsystem,
)

@pytest.fixture
def config():
    return FizzBlockConfig()

@pytest.fixture
def device_mgr(config):
    dm = BlockDeviceManager(config)
    dm.create_device("sda", 104857600)  # 100 MB
    dm.create_device("sdb", 104857600)  # 100 MB
    return dm

@pytest.fixture
def subsystem():
    return create_fizzblock_subsystem()


class TestBlockDeviceManager:
    def test_create_device(self, config):
        dm = BlockDeviceManager(config)
        dev = dm.create_device("sda", 1048576)
        assert dev.name == "sda"
        assert dev.size_bytes == 1048576
        assert dev.sector_count == 1048576 // 4096

    def test_read_write_sector(self, config):
        dm = BlockDeviceManager(config)
        dev = dm.create_device("sda", 1048576)
        data = b"\x42" * 4096
        dm.write_sector(dev, 0, data)
        assert dm.read_sector(dev, 0) == data
        assert dev.write_count == 1
        assert dev.read_count == 1

    def test_read_unwritten_sector(self, config):
        dm = BlockDeviceManager(config)
        dev = dm.create_device("sda", 1048576)
        data = dm.read_sector(dev, 5)
        assert data == b"\x00" * 4096

    def test_out_of_range(self, config):
        dm = BlockDeviceManager(config)
        dev = dm.create_device("sda", 4096)
        with pytest.raises(Exception):
            dm.read_sector(dev, 100)

    def test_delete_device(self, config):
        dm = BlockDeviceManager(config)
        dm.create_device("sda", 4096)
        assert dm.delete_device("sda")
        assert dm.get_device("sda") is None

    def test_list_devices(self, device_mgr):
        assert len(device_mgr.list_devices()) == 2


class TestVolumeManager:
    def test_create_vg(self, config, device_mgr):
        vm = VolumeManager(config, device_mgr)
        vg = vm.create_vg("vg0", ["sda", "sdb"])
        assert vg.name == "vg0"
        assert vg.total_extents > 0

    def test_create_lv(self, config, device_mgr):
        vm = VolumeManager(config, device_mgr)
        vm.create_vg("vg0", ["sda"])
        lv = vm.create_lv("vg0", "data", 524288)
        assert lv.name == "data"
        assert lv.size_bytes == 524288

    def test_create_lv_no_space(self, config, device_mgr):
        vm = VolumeManager(config, device_mgr)
        vm.create_vg("vg0", ["sda"])
        with pytest.raises(Exception):
            vm.create_lv("vg0", "huge", 999999999999)

    def test_delete_lv(self, config, device_mgr):
        vm = VolumeManager(config, device_mgr)
        vm.create_vg("vg0", ["sda"])
        vm.create_lv("vg0", "data", 524288)
        vm.delete_lv("vg0", "data")
        assert vm.get_lv("vg0", "data") is None

    def test_resize_lv(self, config, device_mgr):
        vm = VolumeManager(config, device_mgr)
        vm.create_vg("vg0", ["sda"])
        vm.create_lv("vg0", "data", 524288)
        vm.resize_lv("vg0", "data", 262144)
        lv = vm.get_lv("vg0", "data")
        assert lv.size_bytes == 262144

    def test_snapshot(self, config, device_mgr):
        vm = VolumeManager(config, device_mgr)
        vm.create_vg("vg0", ["sda"])
        vm.create_lv("vg0", "data", 524288)
        snap = vm.create_snapshot("vg0", "data", "data-snap")
        assert snap.state == VolumeState.SNAPSHOT
        assert snap.snapshot_origin == "data"

    def test_list_lvs(self, config, device_mgr):
        vm = VolumeManager(config, device_mgr)
        vm.create_vg("vg0", ["sda"])
        vm.create_lv("vg0", "a", 262144)
        vm.create_lv("vg0", "b", 262144)
        assert len(vm.list_lvs()) == 2


class TestRAIDController:
    def test_create_raid1(self, device_mgr):
        rc = RAIDController(device_mgr)
        arr = rc.create_array("md0", RAIDLevel.RAID1, ["sda", "sdb"])
        assert arr.level == RAIDLevel.RAID1
        assert len(arr.devices) == 2

    def test_create_raid5_insufficient(self, config):
        dm = BlockDeviceManager(config)
        dm.create_device("a", 1024)
        dm.create_device("b", 1024)
        rc = RAIDController(dm)
        with pytest.raises(Exception):
            rc.create_array("md0", RAIDLevel.RAID5, ["a", "b"])  # Need 3

    def test_usable_size_raid0(self, device_mgr):
        rc = RAIDController(device_mgr)
        arr = rc.create_array("md0", RAIDLevel.RAID0, ["sda", "sdb"])
        assert rc.compute_usable_size(arr) == 2 * 104857600

    def test_usable_size_raid1(self, device_mgr):
        rc = RAIDController(device_mgr)
        arr = rc.create_array("md0", RAIDLevel.RAID1, ["sda", "sdb"])
        assert rc.compute_usable_size(arr) == 104857600

    def test_degrade_and_rebuild(self, device_mgr):
        rc = RAIDController(device_mgr)
        arr = rc.create_array("md0", RAIDLevel.RAID1, ["sda", "sdb"])
        rc.degrade_device("md0", 0)
        assert arr.state == "degraded"
        rc.rebuild("md0")
        rc.rebuild("md0")
        rc.rebuild("md0")
        rc.rebuild("md0")
        assert arr.state == "active"


class TestIOScheduler:
    def test_fifo(self):
        s = IOScheduler(IOSchedulerType.FIFO)
        s.submit(IORequest(operation="read", sector=1))
        s.submit(IORequest(operation="read", sector=2))
        r = s.dispatch()
        assert r.sector == 1

    def test_deadline(self):
        s = IOScheduler(IOSchedulerType.DEADLINE)
        s.submit(IORequest(operation="read", sector=1))
        r = s.dispatch()
        assert r is not None

    def test_empty_queue(self):
        s = IOScheduler()
        assert s.dispatch() is None

    def test_processed_count(self):
        s = IOScheduler()
        s.submit(IORequest())
        s.dispatch()
        assert s.processed == 1


class TestBlockEncryptor:
    def test_encrypt_decrypt(self):
        enc = BlockEncryptor()
        data = b"Hello FizzBuzz!" + b"\x00" * (4096 - 15)
        encrypted = enc.encrypt(data, 0)
        assert encrypted != data
        decrypted = enc.decrypt(encrypted, 0)
        assert decrypted == data

    def test_different_sectors(self):
        enc = BlockEncryptor()
        data = b"\x42" * 32
        e1 = enc.encrypt(data, 0)
        e2 = enc.encrypt(data, 1)
        assert e1 != e2


class TestBlockDeduplicator:
    def test_first_block_not_dup(self):
        dd = BlockDeduplicator()
        is_dup, fp = dd.check(b"unique data")
        assert is_dup is False
        assert dd.unique_blocks == 1

    def test_duplicate_detected(self):
        dd = BlockDeduplicator()
        dd.check(b"same data")
        is_dup, _ = dd.check(b"same data")
        assert is_dup is True
        assert dd.savings_bytes > 0


class TestBlockCompressor:
    def test_none(self):
        c = BlockCompressor(CompressionAlgo.NONE)
        data = b"test"
        assert c.compress(data) == data

    def test_lz4_roundtrip(self):
        c = BlockCompressor(CompressionAlgo.LZ4)
        data = b"A" * 1000
        compressed = c.compress(data)
        assert len(compressed) < len(data)
        assert c.decompress(compressed) == data

    def test_ratio(self):
        c = BlockCompressor(CompressionAlgo.ZSTD)
        c.compress(b"A" * 1000)
        assert c.ratio > 1.0


class TestQoSEnforcer:
    def test_allow(self, config):
        qos = QoSEnforcer(config)
        assert qos.check(4096) is True

    def test_iops_limit(self):
        config = FizzBlockConfig(iops_limit=2)
        qos = QoSEnforcer(config)
        qos.check(1)
        qos.check(1)
        assert qos.check(1) is False
        assert qos.throttled_count == 1


class TestStorageTiering:
    def test_cold_default(self):
        t = StorageTieringEngine()
        assert t.recommend_tier("vol") == StorageTier.COLD

    def test_hot_after_access(self):
        t = StorageTieringEngine()
        for _ in range(200):
            t.record_access("vol")
        assert t.recommend_tier("vol") == StorageTier.HOT


class TestBlockStorageEngine:
    def test_started(self, subsystem):
        e, _, _ = subsystem
        assert e.is_running
        assert e.uptime > 0

    def test_metrics(self, subsystem):
        e, _, _ = subsystem
        m = e.get_metrics()
        assert m.total_devices >= 3
        assert m.total_logical_volumes >= 3


class TestFizzBlockMiddleware:
    def test_get_name(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_name() == "fizzblock"

    def test_get_priority(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_priority() == MIDDLEWARE_PRIORITY

    def test_process(self, subsystem):
        _, _, mw = subsystem
        ctx = MagicMock(); ctx.metadata = {}
        mw.process(ctx, None)
        assert ctx.metadata["fizzblock_version"] == FIZZBLOCK_VERSION

    def test_render_dashboard(self, subsystem):
        _, _, mw = subsystem
        assert "FizzBlock" in mw.render_dashboard()

    def test_render_status(self, subsystem):
        _, _, mw = subsystem
        assert "UP" in mw.render_status()

    def test_render_volumes(self, subsystem):
        _, _, mw = subsystem
        assert "fizzbuzz-data" in mw.render_volumes()


class TestCreateSubsystem:
    def test_returns_tuple(self):
        assert len(create_fizzblock_subsystem()) == 3

    def test_default_volumes(self):
        e, _, _ = create_fizzblock_subsystem()
        names = [lv.name for lv in e.volumes.list_lvs()]
        assert "fizzbuzz-data" in names
        assert "fizzbuzz-logs" in names
        assert "fizzbuzz-swap" in names


class TestConstants:
    def test_version(self):
        assert FIZZBLOCK_VERSION == "1.0.0"
    def test_priority(self):
        assert MIDDLEWARE_PRIORITY == 128

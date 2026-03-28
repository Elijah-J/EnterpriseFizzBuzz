"""
Enterprise FizzBuzz Platform - FizzCgroup Test Suite

Comprehensive tests for the Control Group Resource Accounting & Limiting
Engine.  Validates all four controller types (CPU, MEMORY, IO, PIDS),
the OOM killer with three policies, the unified hierarchy, the
CgroupManager singleton, the ResourceAccountant, the dashboard,
middleware integration, factory function wiring, and all 19 exception
classes.  Resource enforcement demands the same verification rigor
applied to every other subsystem.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fizzcgroup import (
    DEFAULT_CPU_PERIOD,
    DEFAULT_CPU_QUOTA,
    DEFAULT_CPU_WEIGHT,
    DEFAULT_DASHBOARD_WIDTH,
    DEFAULT_IO_RBPS_MAX,
    DEFAULT_IO_WBPS_MAX,
    DEFAULT_IO_WEIGHT,
    DEFAULT_MEMORY_HIGH,
    DEFAULT_MEMORY_LOW,
    DEFAULT_MEMORY_MAX,
    DEFAULT_MEMORY_MIN,
    DEFAULT_PIDS_MAX,
    DEFAULT_SWAP_MAX,
    IO_RATE_WINDOW_SECONDS,
    MAX_CGROUP_DEPTH,
    MAX_CPU_PERIOD,
    MAX_CPU_WEIGHT,
    MAX_IO_WEIGHT,
    MIN_CPU_PERIOD,
    MIN_CPU_QUOTA,
    MIN_CPU_WEIGHT,
    MIN_IO_WEIGHT,
    OOM_SCORE_ADJ_MAX,
    OOM_SCORE_ADJ_MIN,
    ROOT_CGROUP_PATH,
    CGROUP_PATH_SEPARATOR,
    CPUConfig,
    CPUController,
    CPUStats,
    CgroupControllerType,
    CgroupHierarchy,
    CgroupManager,
    CgroupNode,
    CgroupState,
    FizzCgroupDashboard,
    FizzCgroupMiddleware,
    IOConfig,
    IOController,
    IOStats,
    MemoryConfig,
    MemoryController,
    MemoryStats,
    OOMEvent,
    OOMKiller,
    OOMPolicy,
    PIDsConfig,
    PIDsController,
    PIDsStats,
    ResourceAccountant,
    ResourceReport,
    ThrottleState,
    create_fizzcgroup_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    CgroupAttachError,
    CgroupControllerError,
    CgroupCreationError,
    CgroupDashboardError,
    CgroupDelegationError,
    CgroupError,
    CgroupHierarchyError,
    CgroupManagerError,
    CgroupMiddlewareError,
    CgroupMigrationError,
    CgroupQuotaExceededError,
    CgroupRemovalError,
    CgroupThrottleError,
    CPUControllerError,
    IOControllerError,
    MemoryControllerError,
    OOMKillerError,
    PIDsControllerError,
    ResourceAccountantError,
)
from enterprise_fizzbuzz.domain.exceptions.cgroups import (
    CgroupDelegationError as CgroupsDelegationError,
)
from config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzcgroup import _CgroupManagerMeta
from models import FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    _CgroupManagerMeta.reset()
    yield
    _SingletonMeta.reset()
    _CgroupManagerMeta.reset()


# ============================================================
# Constants Tests
# ============================================================


class TestConstants:
    """Validate cgroup constants match kernel definitions."""

    def test_default_cpu_weight(self):
        assert DEFAULT_CPU_WEIGHT == 100

    def test_min_cpu_weight(self):
        assert MIN_CPU_WEIGHT == 1

    def test_max_cpu_weight(self):
        assert MAX_CPU_WEIGHT == 10000

    def test_default_cpu_quota(self):
        assert DEFAULT_CPU_QUOTA == -1

    def test_default_cpu_period(self):
        assert DEFAULT_CPU_PERIOD == 100000

    def test_min_cpu_period(self):
        assert MIN_CPU_PERIOD == 1000

    def test_max_cpu_period(self):
        assert MAX_CPU_PERIOD == 1000000

    def test_min_cpu_quota(self):
        assert MIN_CPU_QUOTA == 1000

    def test_default_memory_max(self):
        assert DEFAULT_MEMORY_MAX == -1

    def test_default_memory_high(self):
        assert DEFAULT_MEMORY_HIGH == -1

    def test_default_memory_low(self):
        assert DEFAULT_MEMORY_LOW == 0

    def test_default_memory_min(self):
        assert DEFAULT_MEMORY_MIN == 0

    def test_default_swap_max(self):
        assert DEFAULT_SWAP_MAX == -1

    def test_default_io_weight(self):
        assert DEFAULT_IO_WEIGHT == 100

    def test_min_io_weight(self):
        assert MIN_IO_WEIGHT == 1

    def test_max_io_weight(self):
        assert MAX_IO_WEIGHT == 10000

    def test_default_pids_max(self):
        assert DEFAULT_PIDS_MAX == -1

    def test_max_cgroup_depth(self):
        assert MAX_CGROUP_DEPTH == 32

    def test_root_cgroup_path(self):
        assert ROOT_CGROUP_PATH == "/"

    def test_default_dashboard_width(self):
        assert DEFAULT_DASHBOARD_WIDTH == 72

    def test_oom_score_adj_min(self):
        assert OOM_SCORE_ADJ_MIN == -1000

    def test_oom_score_adj_max(self):
        assert OOM_SCORE_ADJ_MAX == 1000

    def test_io_rate_window(self):
        assert IO_RATE_WINDOW_SECONDS == 5.0

    def test_cgroup_path_separator(self):
        assert CGROUP_PATH_SEPARATOR == "/"


# ============================================================
# CgroupControllerType Enum Tests
# ============================================================


class TestCgroupControllerType:
    """Validate CgroupControllerType enum members."""

    def test_cpu_value(self):
        assert CgroupControllerType.CPU.value == "cpu"

    def test_memory_value(self):
        assert CgroupControllerType.MEMORY.value == "memory"

    def test_io_value(self):
        assert CgroupControllerType.IO.value == "io"

    def test_pids_value(self):
        assert CgroupControllerType.PIDS.value == "pids"

    def test_member_count(self):
        assert len(CgroupControllerType) == 4

    def test_all_unique_values(self):
        values = [t.value for t in CgroupControllerType]
        assert len(values) == len(set(values))

    def test_cpu_name(self):
        assert CgroupControllerType.CPU.name == "CPU"

    def test_memory_name(self):
        assert CgroupControllerType.MEMORY.name == "MEMORY"

    def test_io_name(self):
        assert CgroupControllerType.IO.name == "IO"

    def test_pids_name(self):
        assert CgroupControllerType.PIDS.name == "PIDS"


# ============================================================
# CgroupState Enum Tests
# ============================================================


class TestCgroupState:
    """Validate CgroupState enum members."""

    def test_active_value(self):
        assert CgroupState.ACTIVE.value == "active"

    def test_draining_value(self):
        assert CgroupState.DRAINING.value == "draining"

    def test_removed_value(self):
        assert CgroupState.REMOVED.value == "removed"

    def test_member_count(self):
        assert len(CgroupState) == 3


# ============================================================
# OOMPolicy Enum Tests
# ============================================================


class TestOOMPolicy:
    """Validate OOMPolicy enum members."""

    def test_kill_largest_value(self):
        assert OOMPolicy.KILL_LARGEST.value == "kill_largest"

    def test_kill_oldest_value(self):
        assert OOMPolicy.KILL_OLDEST.value == "kill_oldest"

    def test_kill_lowest_priority_value(self):
        assert OOMPolicy.KILL_LOWEST_PRIORITY.value == "kill_lowest_priority"

    def test_member_count(self):
        assert len(OOMPolicy) == 3


# ============================================================
# ThrottleState Enum Tests
# ============================================================


class TestThrottleState:
    """Validate ThrottleState enum members."""

    def test_running_value(self):
        assert ThrottleState.RUNNING.value == "running"

    def test_throttled_value(self):
        assert ThrottleState.THROTTLED.value == "throttled"

    def test_member_count(self):
        assert len(ThrottleState) == 2


# ============================================================
# CPUStats Dataclass Tests
# ============================================================


class TestCPUStats:
    """Validate CPUStats dataclass defaults and fields."""

    def test_default_usage_usec(self):
        stats = CPUStats()
        assert stats.usage_usec == 0

    def test_default_user_usec(self):
        stats = CPUStats()
        assert stats.user_usec == 0

    def test_default_system_usec(self):
        stats = CPUStats()
        assert stats.system_usec == 0

    def test_default_nr_periods(self):
        stats = CPUStats()
        assert stats.nr_periods == 0

    def test_default_nr_throttled(self):
        stats = CPUStats()
        assert stats.nr_throttled == 0

    def test_default_throttled_usec(self):
        stats = CPUStats()
        assert stats.throttled_usec == 0

    def test_custom_values(self):
        stats = CPUStats(usage_usec=1000, user_usec=700, system_usec=300)
        assert stats.usage_usec == 1000
        assert stats.user_usec == 700
        assert stats.system_usec == 300


# ============================================================
# MemoryStats Dataclass Tests
# ============================================================


class TestMemoryStats:
    """Validate MemoryStats dataclass defaults."""

    def test_default_current(self):
        stats = MemoryStats()
        assert stats.current == 0

    def test_default_rss(self):
        stats = MemoryStats()
        assert stats.rss == 0

    def test_default_cache(self):
        stats = MemoryStats()
        assert stats.cache == 0

    def test_default_swap(self):
        stats = MemoryStats()
        assert stats.swap == 0

    def test_default_kernel(self):
        stats = MemoryStats()
        assert stats.kernel == 0

    def test_default_oom_kills(self):
        stats = MemoryStats()
        assert stats.oom_kills == 0


# ============================================================
# IOStats Dataclass Tests
# ============================================================


class TestIOStats:
    """Validate IOStats dataclass defaults."""

    def test_default_rbytes(self):
        stats = IOStats()
        assert stats.rbytes == 0

    def test_default_wbytes(self):
        stats = IOStats()
        assert stats.wbytes == 0

    def test_default_rios(self):
        stats = IOStats()
        assert stats.rios == 0

    def test_default_wios(self):
        stats = IOStats()
        assert stats.wios == 0


# ============================================================
# PIDsStats Dataclass Tests
# ============================================================


class TestPIDsStats:
    """Validate PIDsStats dataclass defaults."""

    def test_default_current(self):
        stats = PIDsStats()
        assert stats.current == 0

    def test_default_limit(self):
        stats = PIDsStats()
        assert stats.limit == -1

    def test_default_denied(self):
        stats = PIDsStats()
        assert stats.denied == 0


# ============================================================
# CPUConfig Dataclass Tests
# ============================================================


class TestCPUConfig:
    """Validate CPUConfig dataclass defaults."""

    def test_default_weight(self):
        cfg = CPUConfig()
        assert cfg.weight == DEFAULT_CPU_WEIGHT

    def test_default_quota(self):
        cfg = CPUConfig()
        assert cfg.quota == DEFAULT_CPU_QUOTA

    def test_default_period(self):
        cfg = CPUConfig()
        assert cfg.period == DEFAULT_CPU_PERIOD

    def test_custom_values(self):
        cfg = CPUConfig(weight=200, quota=50000, period=100000)
        assert cfg.weight == 200
        assert cfg.quota == 50000
        assert cfg.period == 100000


# ============================================================
# MemoryConfig Dataclass Tests
# ============================================================


class TestMemoryConfig:
    """Validate MemoryConfig dataclass defaults."""

    def test_default_max(self):
        cfg = MemoryConfig()
        assert cfg.max == DEFAULT_MEMORY_MAX

    def test_default_high(self):
        cfg = MemoryConfig()
        assert cfg.high == DEFAULT_MEMORY_HIGH

    def test_default_low(self):
        cfg = MemoryConfig()
        assert cfg.low == DEFAULT_MEMORY_LOW

    def test_default_min(self):
        cfg = MemoryConfig()
        assert cfg.min == DEFAULT_MEMORY_MIN

    def test_default_swap_max(self):
        cfg = MemoryConfig()
        assert cfg.swap_max == DEFAULT_SWAP_MAX

    def test_default_oom_policy(self):
        cfg = MemoryConfig()
        assert cfg.oom_policy == OOMPolicy.KILL_LARGEST


# ============================================================
# IOConfig Dataclass Tests
# ============================================================


class TestIOConfig:
    """Validate IOConfig dataclass defaults."""

    def test_default_weight(self):
        cfg = IOConfig()
        assert cfg.weight == DEFAULT_IO_WEIGHT

    def test_default_rbps_max(self):
        cfg = IOConfig()
        assert cfg.rbps_max == DEFAULT_IO_RBPS_MAX

    def test_default_wbps_max(self):
        cfg = IOConfig()
        assert cfg.wbps_max == DEFAULT_IO_WBPS_MAX


# ============================================================
# PIDsConfig Dataclass Tests
# ============================================================


class TestPIDsConfig:
    """Validate PIDsConfig dataclass defaults."""

    def test_default_max(self):
        cfg = PIDsConfig()
        assert cfg.max == DEFAULT_PIDS_MAX


# ============================================================
# ResourceReport Dataclass Tests
# ============================================================


class TestResourceReport:
    """Validate ResourceReport dataclass defaults."""

    def test_default_path(self):
        r = ResourceReport()
        assert r.cgroup_path == ""

    def test_default_cpu_pct(self):
        r = ResourceReport()
        assert r.cpu_utilization_pct == 0.0

    def test_default_memory_pct(self):
        r = ResourceReport()
        assert r.memory_utilization_pct == 0.0


# ============================================================
# OOMEvent Dataclass Tests
# ============================================================


class TestOOMEvent:
    """Validate OOMEvent dataclass defaults."""

    def test_default_victim_pid(self):
        e = OOMEvent()
        assert e.victim_pid == 0

    def test_default_policy(self):
        e = OOMEvent()
        assert e.policy == OOMPolicy.KILL_LARGEST

    def test_default_score(self):
        e = OOMEvent()
        assert e.score == 0.0


# ============================================================
# CPUController Tests
# ============================================================


class TestCPUController:
    """Validate CPU controller weight, bandwidth, throttling, and accounting."""

    def test_default_initialization(self):
        cpu = CPUController()
        assert cpu.weight == DEFAULT_CPU_WEIGHT
        assert cpu.quota == DEFAULT_CPU_QUOTA
        assert cpu.period == DEFAULT_CPU_PERIOD

    def test_custom_weight(self):
        cpu = CPUController(config=CPUConfig(weight=500))
        assert cpu.weight == 500

    def test_set_weight(self):
        cpu = CPUController()
        cpu.set_weight(200)
        assert cpu.weight == 200

    def test_set_weight_min(self):
        cpu = CPUController()
        cpu.set_weight(MIN_CPU_WEIGHT)
        assert cpu.weight == MIN_CPU_WEIGHT

    def test_set_weight_max(self):
        cpu = CPUController()
        cpu.set_weight(MAX_CPU_WEIGHT)
        assert cpu.weight == MAX_CPU_WEIGHT

    def test_set_weight_below_min(self):
        cpu = CPUController()
        with pytest.raises(CPUControllerError):
            cpu.set_weight(0)

    def test_set_weight_above_max(self):
        cpu = CPUController()
        with pytest.raises(CPUControllerError):
            cpu.set_weight(MAX_CPU_WEIGHT + 1)

    def test_invalid_weight_init(self):
        with pytest.raises(CPUControllerError):
            CPUController(config=CPUConfig(weight=0))

    def test_set_bandwidth(self):
        cpu = CPUController()
        cpu.set_bandwidth(50000, 100000)
        assert cpu.quota == 50000
        assert cpu.period == 100000

    def test_set_bandwidth_max(self):
        cpu = CPUController()
        cpu.set_bandwidth(-1)
        assert cpu.quota == -1

    def test_invalid_quota(self):
        cpu = CPUController()
        with pytest.raises(CPUControllerError):
            cpu.set_bandwidth(500)  # Below MIN_CPU_QUOTA

    def test_invalid_period_low(self):
        cpu = CPUController()
        with pytest.raises(CPUControllerError):
            cpu.set_bandwidth(50000, 500)

    def test_invalid_period_high(self):
        cpu = CPUController()
        with pytest.raises(CPUControllerError):
            cpu.set_bandwidth(50000, MAX_CPU_PERIOD + 1)

    def test_charge_basic(self):
        cpu = CPUController()
        result = cpu.charge(1000)
        assert result is True
        assert cpu.stats.usage_usec == 1000

    def test_charge_user_system_split(self):
        cpu = CPUController()
        cpu.charge(1000, user_pct=0.6)
        assert cpu.stats.user_usec == 600
        assert cpu.stats.system_usec == 400

    def test_charge_negative(self):
        cpu = CPUController()
        with pytest.raises(CPUControllerError):
            cpu.charge(-100)

    def test_charge_zero(self):
        cpu = CPUController()
        result = cpu.charge(0)
        assert result is True

    def test_throttle_on_quota_exceeded(self):
        cpu = CPUController(config=CPUConfig(quota=5000, period=100000))
        cpu.charge(3000)
        assert cpu.is_throttled() is False
        cpu.charge(3000)  # Total 6000 > 5000 quota
        assert cpu.is_throttled() is True

    def test_throttle_state_running(self):
        cpu = CPUController()
        assert cpu.throttle_state == ThrottleState.RUNNING

    def test_throttle_returns_false(self):
        cpu = CPUController(config=CPUConfig(quota=1000, period=100000))
        cpu.charge(500)
        result = cpu.charge(600)  # Exceeds quota
        assert result is False

    def test_reset_period(self):
        cpu = CPUController(config=CPUConfig(quota=1000, period=100000))
        cpu.charge(1500)
        assert cpu.is_throttled() is True
        cpu.reset_period()
        assert cpu.is_throttled() is False

    def test_get_utilization_with_quota(self):
        cpu = CPUController(config=CPUConfig(quota=10000, period=100000))
        cpu.charge(5000)
        util = cpu.get_utilization()
        assert util == pytest.approx(50.0)

    def test_get_utilization_no_quota(self):
        cpu = CPUController()
        # No quota -> relative to one core
        util = cpu.get_utilization()
        assert util >= 0.0

    def test_get_effective_cpus_half(self):
        cpu = CPUController(config=CPUConfig(quota=50000, period=100000))
        assert cpu.get_effective_cpus() == 0.5

    def test_get_effective_cpus_two(self):
        cpu = CPUController(config=CPUConfig(quota=200000, period=100000))
        assert cpu.get_effective_cpus() == 2.0

    def test_get_effective_cpus_unlimited(self):
        cpu = CPUController()
        assert cpu.get_effective_cpus() == float("inf")

    def test_get_weight_share(self):
        cpu = CPUController(config=CPUConfig(weight=200))
        share = cpu.get_weight_share(1000)
        assert share == pytest.approx(0.2)

    def test_get_weight_share_zero_total(self):
        cpu = CPUController()
        assert cpu.get_weight_share(0) == 1.0

    def test_get_throttle_ratio_no_periods(self):
        cpu = CPUController()
        assert cpu.get_throttle_ratio() == 0.0

    def test_total_charge_accumulates(self):
        cpu = CPUController()
        cpu.charge(100)
        cpu.charge(200)
        assert cpu.total_charge == 300

    def test_to_dict(self):
        cpu = CPUController(config=CPUConfig(weight=150))
        d = cpu.to_dict()
        assert d["controller"] == "cpu"
        assert d["weight"] == 150

    def test_repr(self):
        cpu = CPUController()
        r = repr(cpu)
        assert "CPUController" in r
        assert "weight=100" in r

    def test_config_property(self):
        cpu = CPUController()
        assert isinstance(cpu.config, CPUConfig)


# ============================================================
# MemoryController Tests
# ============================================================


class TestMemoryController:
    """Validate memory controller limits, charging, OOM, and accounting."""

    def test_default_initialization(self):
        mem = MemoryController()
        assert mem.current == 0
        assert mem.config.max == DEFAULT_MEMORY_MAX

    def test_charge_rss(self):
        mem = MemoryController()
        result = mem.charge(1, 1024, "rss")
        assert result is True
        assert mem.stats.rss == 1024
        assert mem.current == 1024

    def test_charge_cache(self):
        mem = MemoryController()
        mem.charge(1, 512, "cache")
        assert mem.stats.cache == 512
        assert mem.current == 512

    def test_charge_kernel(self):
        mem = MemoryController()
        mem.charge(1, 256, "kernel")
        assert mem.stats.kernel == 256
        assert mem.current == 256

    def test_charge_swap(self):
        mem = MemoryController()
        mem.charge(1, 128, "swap")
        assert mem.stats.swap == 128
        assert mem.current == 0  # Swap doesn't count toward current

    def test_charge_negative(self):
        mem = MemoryController()
        with pytest.raises(MemoryControllerError):
            mem.charge(1, -100)

    def test_charge_unknown_category(self):
        mem = MemoryController()
        with pytest.raises(MemoryControllerError):
            mem.charge(1, 100, "unknown")

    def test_charge_zero(self):
        mem = MemoryController()
        result = mem.charge(1, 0)
        assert result is True

    def test_max_limit_triggers_oom(self):
        callback = MagicMock()
        mem = MemoryController(
            config=MemoryConfig(max=1000),
            oom_trigger_callback=callback,
        )
        mem.charge(1, 800, "rss")
        result = mem.charge(1, 300, "rss")
        assert result is False
        assert callback.called

    def test_max_limit_without_callback(self):
        mem = MemoryController(config=MemoryConfig(max=1000))
        mem.charge(1, 800, "rss")
        result = mem.charge(1, 300, "rss")
        assert result is False

    def test_high_triggers_throttle(self):
        mem = MemoryController(config=MemoryConfig(high=500))
        mem.charge(1, 600, "rss")
        assert mem.is_throttled is True
        assert mem.stats.high_events == 1

    def test_release_rss(self):
        mem = MemoryController()
        mem.charge(1, 1024, "rss")
        mem.release(1, 512, "rss")
        assert mem.stats.rss == 512
        assert mem.current == 512

    def test_release_cache(self):
        mem = MemoryController()
        mem.charge(1, 1024, "cache")
        mem.release(1, 300, "cache")
        assert mem.stats.cache == 724

    def test_release_swap(self):
        mem = MemoryController()
        mem.charge(1, 1024, "swap")
        mem.release(1, 500, "swap")
        assert mem.stats.swap == 524

    def test_release_negative(self):
        mem = MemoryController()
        with pytest.raises(MemoryControllerError):
            mem.release(1, -100)

    def test_release_unknown_category(self):
        mem = MemoryController()
        with pytest.raises(MemoryControllerError):
            mem.release(1, 100, "unknown")

    def test_release_zero(self):
        mem = MemoryController()
        mem.charge(1, 100, "rss")
        mem.release(1, 0, "rss")
        assert mem.current == 100

    def test_release_all_for_pid(self):
        mem = MemoryController()
        mem.charge(1, 1024, "rss")
        mem.charge(2, 512, "rss")
        mem.release_all_for_pid(1)
        assert mem.get_process_charge(1) == 0
        assert mem.current == 512

    def test_release_lifts_throttle(self):
        mem = MemoryController(config=MemoryConfig(high=500))
        mem.charge(1, 600, "rss")
        assert mem.is_throttled is True
        mem.release(1, 200, "rss")
        assert mem.is_throttled is False

    def test_set_max(self):
        mem = MemoryController()
        mem.set_max(2048)
        assert mem.config.max == 2048

    def test_set_max_unlimited(self):
        mem = MemoryController()
        mem.set_max(-1)
        assert mem.config.max == -1

    def test_set_max_invalid(self):
        mem = MemoryController()
        with pytest.raises(MemoryControllerError):
            mem.set_max(-5)

    def test_set_high(self):
        mem = MemoryController()
        mem.set_high(1024)
        assert mem.config.high == 1024

    def test_set_high_below_low(self):
        mem = MemoryController(config=MemoryConfig(low=100))
        with pytest.raises(MemoryControllerError):
            mem.set_high(50)

    def test_set_low(self):
        mem = MemoryController()
        mem.set_low(256)
        assert mem.config.low == 256

    def test_set_low_below_min(self):
        mem = MemoryController(config=MemoryConfig(min=100, low=200))
        with pytest.raises(MemoryControllerError):
            mem.set_low(50)

    def test_set_min(self):
        mem = MemoryController()
        mem.set_min(0)
        assert mem.config.min == 0

    def test_set_min_negative(self):
        mem = MemoryController()
        with pytest.raises(MemoryControllerError):
            mem.set_min(-1)

    def test_get_utilization(self):
        mem = MemoryController(config=MemoryConfig(max=1000))
        mem.charge(1, 500, "rss")
        assert mem.get_utilization() == pytest.approx(50.0)

    def test_get_utilization_unlimited(self):
        mem = MemoryController()
        assert mem.get_utilization() == 0.0

    def test_get_available(self):
        mem = MemoryController(config=MemoryConfig(max=1000))
        mem.charge(1, 300, "rss")
        assert mem.get_available() == 700

    def test_get_available_unlimited(self):
        mem = MemoryController()
        assert mem.get_available() == -1

    def test_is_under_pressure(self):
        mem = MemoryController(config=MemoryConfig(high=500))
        assert mem.is_under_pressure() is False
        mem.charge(1, 600, "rss")
        assert mem.is_under_pressure() is True

    def test_is_protected(self):
        mem = MemoryController(config=MemoryConfig(min=100, low=200))
        assert mem.is_protected(50) is True
        assert mem.is_protected(150) is True
        assert mem.is_protected(250) is False

    def test_charges_per_process(self):
        mem = MemoryController()
        mem.charge(1, 100, "rss")
        mem.charge(2, 200, "rss")
        assert mem.get_process_charge(1) == 100
        assert mem.get_process_charge(2) == 200
        assert mem.get_process_charge(999) == 0

    def test_charges_property(self):
        mem = MemoryController()
        mem.charge(1, 100, "rss")
        charges = mem.charges
        assert 1 in charges
        assert charges[1] == 100

    def test_swap_limit(self):
        mem = MemoryController(config=MemoryConfig(swap_max=100))
        result = mem.charge(1, 50, "swap")
        assert result is True
        result = mem.charge(1, 60, "swap")
        assert result is False

    def test_to_dict(self):
        mem = MemoryController(config=MemoryConfig(max=4096))
        d = mem.to_dict()
        assert d["controller"] == "memory"
        assert d["max"] == 4096

    def test_repr(self):
        mem = MemoryController()
        r = repr(mem)
        assert "MemoryController" in r

    def test_config_validation_min_negative(self):
        with pytest.raises(MemoryControllerError):
            MemoryController(config=MemoryConfig(min=-1))

    def test_config_validation_low_below_min(self):
        with pytest.raises(MemoryControllerError):
            MemoryController(config=MemoryConfig(min=200, low=100))

    def test_config_validation_high_below_low(self):
        with pytest.raises(MemoryControllerError):
            MemoryController(config=MemoryConfig(low=200, high=100))

    def test_config_validation_max_below_high(self):
        with pytest.raises(MemoryControllerError):
            MemoryController(config=MemoryConfig(high=200, max=100))

    def test_max_events_counter(self):
        mem = MemoryController(config=MemoryConfig(max=100))
        mem.charge(1, 50, "rss")
        mem.charge(1, 60, "rss")
        assert mem.stats.max_events == 1


# ============================================================
# IOController Tests
# ============================================================


class TestIOController:
    """Validate I/O controller bandwidth throttling and accounting."""

    def test_default_initialization(self):
        io = IOController()
        assert io.weight == DEFAULT_IO_WEIGHT

    def test_set_weight(self):
        io = IOController()
        io.set_weight(500)
        assert io.weight == 500

    def test_set_weight_invalid(self):
        io = IOController()
        with pytest.raises(IOControllerError):
            io.set_weight(0)

    def test_set_weight_above_max(self):
        io = IOController()
        with pytest.raises(IOControllerError):
            io.set_weight(MAX_IO_WEIGHT + 1)

    def test_invalid_weight_init(self):
        with pytest.raises(IOControllerError):
            IOController(config=IOConfig(weight=0))

    def test_charge_read(self):
        io = IOController()
        result = io.charge_read("sda", 4096)
        assert result is True
        assert io.stats.rbytes == 4096
        assert io.stats.rios == 1

    def test_charge_write(self):
        io = IOController()
        result = io.charge_write("sda", 2048)
        assert result is True
        assert io.stats.wbytes == 2048
        assert io.stats.wios == 1

    def test_charge_read_negative(self):
        io = IOController()
        with pytest.raises(IOControllerError):
            io.charge_read("sda", -100)

    def test_charge_write_negative(self):
        io = IOController()
        with pytest.raises(IOControllerError):
            io.charge_write("sda", -100)

    def test_set_limits(self):
        io = IOController()
        io.set_limits(rbps_max=1000, wbps_max=500)
        assert io.config.rbps_max == 1000
        assert io.config.wbps_max == 500

    def test_device_stats(self):
        io = IOController()
        io.charge_read("sda", 1024)
        io.charge_write("sdb", 2048)
        sda = io.get_device_stats("sda")
        sdb = io.get_device_stats("sdb")
        assert sda is not None
        assert sda.rbytes == 1024
        assert sdb is not None
        assert sdb.wbytes == 2048

    def test_device_stats_none(self):
        io = IOController()
        assert io.get_device_stats("nonexistent") is None

    def test_get_devices(self):
        io = IOController()
        io.charge_read("sda", 100)
        io.charge_write("sdb", 200)
        devices = io.get_devices()
        assert "sda" in devices
        assert "sdb" in devices

    def test_get_weight_share(self):
        io = IOController(config=IOConfig(weight=200))
        share = io.get_weight_share(1000)
        assert share == pytest.approx(0.2)

    def test_is_throttled_default(self):
        io = IOController()
        assert io.is_throttled is False

    def test_to_dict(self):
        io = IOController()
        d = io.to_dict()
        assert d["controller"] == "io"

    def test_repr(self):
        io = IOController()
        r = repr(io)
        assert "IOController" in r

    def test_config_property(self):
        io = IOController()
        assert isinstance(io.config, IOConfig)

    def test_multiple_ops(self):
        io = IOController()
        io.charge_read("sda", 100, ops=5)
        assert io.stats.rios == 5

    def test_multiple_writes(self):
        io = IOController()
        io.charge_write("sda", 100, ops=3)
        assert io.stats.wios == 3


# ============================================================
# PIDsController Tests
# ============================================================


class TestPIDsController:
    """Validate PIDs controller process limiting and fork gating."""

    def test_default_initialization(self):
        pids = PIDsController()
        assert pids.current == 0
        assert pids.limit == DEFAULT_PIDS_MAX

    def test_fork_unlimited(self):
        pids = PIDsController()
        result = pids.fork(1)
        assert result is True
        assert pids.current == 1

    def test_fork_limited(self):
        pids = PIDsController(config=PIDsConfig(max=2))
        assert pids.fork(1) is True
        assert pids.fork(2) is True
        assert pids.fork(3) is False

    def test_fork_denied_counter(self):
        pids = PIDsController(config=PIDsConfig(max=1))
        pids.fork(1)
        pids.fork(2)
        pids.fork(3)
        assert pids.stats.denied == 2

    def test_exit(self):
        pids = PIDsController()
        pids.fork(1)
        pids.fork(2)
        pids.exit(1)
        assert pids.current == 1

    def test_can_fork_true(self):
        pids = PIDsController(config=PIDsConfig(max=5))
        assert pids.can_fork() is True

    def test_can_fork_false(self):
        pids = PIDsController(config=PIDsConfig(max=1))
        pids.fork(1)
        assert pids.can_fork() is False

    def test_add_process(self):
        pids = PIDsController()
        assert pids.add_process(1) is True
        assert pids.current == 1

    def test_add_process_duplicate(self):
        pids = PIDsController()
        pids.add_process(1)
        assert pids.add_process(1) is True
        assert pids.current == 1

    def test_add_process_at_limit(self):
        pids = PIDsController(config=PIDsConfig(max=1))
        pids.add_process(1)
        assert pids.add_process(2) is False

    def test_remove_process(self):
        pids = PIDsController()
        pids.add_process(1)
        pids.remove_process(1)
        assert pids.current == 0

    def test_set_max(self):
        pids = PIDsController()
        pids.set_max(100)
        assert pids.limit == 100

    def test_set_max_invalid(self):
        pids = PIDsController()
        with pytest.raises(PIDsControllerError):
            pids.set_max(-5)

    def test_set_max_unlimited(self):
        pids = PIDsController()
        pids.set_max(-1)
        assert pids.limit == -1

    def test_processes_property(self):
        pids = PIDsController()
        pids.fork(10)
        pids.fork(20)
        procs = pids.processes
        assert 10 in procs
        assert 20 in procs

    def test_to_dict(self):
        pids = PIDsController()
        d = pids.to_dict()
        assert d["controller"] == "pids"

    def test_repr(self):
        pids = PIDsController()
        r = repr(pids)
        assert "PIDsController" in r

    def test_stats_property(self):
        pids = PIDsController()
        assert isinstance(pids.stats, PIDsStats)


# ============================================================
# OOMKiller Tests
# ============================================================


class TestOOMKiller:
    """Validate OOM killer victim selection, scoring, and kill execution."""

    def test_default_policy(self):
        oom = OOMKiller()
        assert oom.policy == OOMPolicy.KILL_LARGEST

    def test_set_policy(self):
        oom = OOMKiller()
        oom.set_policy(OOMPolicy.KILL_OLDEST)
        assert oom.policy == OOMPolicy.KILL_OLDEST

    def test_compute_score_kill_largest(self):
        oom = OOMKiller(policy=OOMPolicy.KILL_LARGEST)
        score = oom.compute_score(1, 500, 1000)
        assert score == pytest.approx(500.0)

    def test_compute_score_oom_adj_min(self):
        oom = OOMKiller()
        oom.set_process_metadata(1, oom_score_adj=OOM_SCORE_ADJ_MIN)
        score = oom.compute_score(1, 500, 1000)
        assert score == -1.0

    def test_compute_score_oom_adj_max(self):
        oom = OOMKiller()
        oom.set_process_metadata(1, oom_score_adj=OOM_SCORE_ADJ_MAX)
        score = oom.compute_score(1, 500, 1000)
        assert score == float("inf")

    def test_oom_score_adj_out_of_range(self):
        oom = OOMKiller()
        with pytest.raises(OOMKillerError):
            oom.set_process_metadata(1, oom_score_adj=2000)

    def test_select_victim_largest(self):
        oom = OOMKiller(policy=OOMPolicy.KILL_LARGEST)
        charges = {1: 100, 2: 500, 3: 200}
        victim = oom.select_victim(charges, 1000)
        assert victim == 2

    def test_select_victim_lowest_priority(self):
        oom = OOMKiller(policy=OOMPolicy.KILL_LOWEST_PRIORITY)
        oom.set_process_metadata(1, priority=10)
        oom.set_process_metadata(2, priority=1)
        oom.set_process_metadata(3, priority=5)
        charges = {1: 100, 2: 100, 3: 100}
        victim = oom.select_victim(charges, 1000)
        assert victim == 2  # Lowest priority -> highest score

    def test_select_victim_empty(self):
        oom = OOMKiller()
        with pytest.raises(OOMKillerError):
            oom.select_victim({}, 1000)

    def test_select_victim_all_protected(self):
        oom = OOMKiller()
        oom.set_process_metadata(1, oom_score_adj=OOM_SCORE_ADJ_MIN)
        with pytest.raises(OOMKillerError):
            oom.select_victim({1: 500}, 1000)

    def test_kill(self):
        oom = OOMKiller()
        event = oom.kill("/test", 1, 500, 1000, 1100)
        assert event.victim_pid == 1
        assert event.cgroup_path == "/test"
        assert event.memory_max == 1000
        assert oom.total_kills == 1

    def test_trigger_oom(self):
        oom = OOMKiller()
        charges = {1: 100, 2: 500}
        event = oom.trigger_oom("/test", charges, 1000, 1100)
        assert event is not None
        assert event.victim_pid == 2

    def test_trigger_oom_with_memory_controller(self):
        oom = OOMKiller()
        mem = MemoryController(config=MemoryConfig(max=1000))
        mem.charge(1, 100, "rss")
        mem.charge(2, 500, "rss")
        event = oom.trigger_oom(
            "/test", {1: 100, 2: 500}, 1000, 600, memory_controller=mem
        )
        assert event is not None
        assert mem.get_process_charge(2) == 0

    def test_trigger_oom_no_eligible(self):
        oom = OOMKiller()
        oom.set_process_metadata(1, oom_score_adj=OOM_SCORE_ADJ_MIN)
        event = oom.trigger_oom("/test", {1: 500}, 1000, 1100)
        assert event is None

    def test_history(self):
        oom = OOMKiller()
        oom.kill("/test", 1, 100, 1000, 1100)
        oom.kill("/test", 2, 200, 1000, 1200)
        assert len(oom.history) == 2

    def test_get_recent_events(self):
        oom = OOMKiller()
        for i in range(15):
            oom.kill("/test", i, i * 10, 1000, 1000)
        recent = oom.get_recent_events(5)
        assert len(recent) == 5
        assert recent[0].victim_pid == 14

    def test_get_statistics(self):
        oom = OOMKiller()
        stats = oom.get_statistics()
        assert stats["total_kills"] == 0
        assert stats["policy"] == "kill_largest"

    def test_remove_process_metadata(self):
        oom = OOMKiller()
        oom.set_process_metadata(1, priority=5)
        oom.remove_process_metadata(1)
        score = oom.compute_score(1, 100, 1000)
        assert score >= 0  # Default scoring, no special metadata

    def test_to_dict(self):
        oom = OOMKiller()
        d = oom.to_dict()
        assert d["policy"] == "kill_largest"

    def test_repr(self):
        oom = OOMKiller()
        r = repr(oom)
        assert "OOMKiller" in r

    def test_oldest_policy_scoring(self):
        oom = OOMKiller(policy=OOMPolicy.KILL_OLDEST)
        oom.set_process_metadata(1, start_time=time.time() - 100)
        oom.set_process_metadata(2, start_time=time.time() - 10)
        charges = {1: 100, 2: 100}
        victim = oom.select_victim(charges, 1000)
        assert victim == 1  # Older process


# ============================================================
# CgroupNode Tests
# ============================================================


class TestCgroupNode:
    """Validate CgroupNode tree structure, controllers, and process management."""

    def test_basic_creation(self):
        node = CgroupNode(name="test", path="/test")
        assert node.name == "test"
        assert node.path == "/test"
        assert node.state == CgroupState.ACTIVE

    def test_cgroup_id_generated(self):
        node = CgroupNode(name="test", path="/test")
        assert node.cgroup_id.startswith("cg-")

    def test_unique_ids(self):
        n1 = CgroupNode(name="a", path="/a")
        n2 = CgroupNode(name="b", path="/b")
        assert n1.cgroup_id != n2.cgroup_id

    def test_parent_none_for_root(self):
        node = CgroupNode(name="root", path="/")
        assert node.parent is None
        assert node.is_root is True

    def test_parent_child_relationship(self):
        parent = CgroupNode(name="parent", path="/parent")
        child = CgroupNode(name="child", path="/parent/child", parent=parent)
        parent.add_child(child)
        assert child.parent == parent
        assert child in parent.children

    def test_remove_child(self):
        parent = CgroupNode(name="parent", path="/parent")
        child = CgroupNode(name="child", path="/parent/child", parent=parent)
        parent.add_child(child)
        parent.remove_child(child)
        assert child not in parent.children

    def test_depth(self):
        root = CgroupNode(name="root", path="/")
        child = CgroupNode(name="child", path="/child", parent=root)
        grandchild = CgroupNode(name="gc", path="/child/gc", parent=child)
        assert root.depth == 0
        assert child.depth == 1
        assert grandchild.depth == 2

    def test_is_leaf(self):
        node = CgroupNode(name="leaf", path="/leaf")
        assert node.is_leaf is True
        child = CgroupNode(name="child", path="/leaf/child", parent=node)
        node.add_child(child)
        assert node.is_leaf is False

    def test_controllers_enabled(self):
        node = CgroupNode(
            name="test", path="/test",
            controllers={CgroupControllerType.CPU, CgroupControllerType.MEMORY},
        )
        assert node.has_controller(CgroupControllerType.CPU)
        assert node.has_controller(CgroupControllerType.MEMORY)
        assert not node.has_controller(CgroupControllerType.IO)

    def test_get_controller(self):
        node = CgroupNode(
            name="test", path="/test",
            controllers={CgroupControllerType.CPU},
        )
        cpu = node.get_controller(CgroupControllerType.CPU)
        assert isinstance(cpu, CPUController)

    def test_get_controller_none(self):
        node = CgroupNode(name="test", path="/test")
        assert node.get_controller(CgroupControllerType.CPU) is None

    def test_attach_process(self):
        node = CgroupNode(name="test", path="/test")
        node.attach_process(1)
        assert 1 in node.processes

    def test_attach_process_inactive(self):
        node = CgroupNode(name="test", path="/test")
        node.mark_removed()
        with pytest.raises(CgroupAttachError):
            node.attach_process(1)

    def test_attach_process_pids_limit(self):
        node = CgroupNode(
            name="test", path="/test",
            controllers={CgroupControllerType.PIDS},
        )
        pids = node.get_controller(CgroupControllerType.PIDS)
        pids.set_max(1)
        node.attach_process(1)
        with pytest.raises(CgroupAttachError):
            node.attach_process(2)

    def test_detach_process(self):
        node = CgroupNode(name="test", path="/test")
        node.attach_process(1)
        node.detach_process(1)
        assert 1 not in node.processes

    def test_subtree_control(self):
        node = CgroupNode(
            name="test", path="/test",
            controllers={CgroupControllerType.CPU, CgroupControllerType.MEMORY},
        )
        node.set_subtree_control({CgroupControllerType.CPU})
        assert CgroupControllerType.CPU in node.subtree_control

    def test_subtree_control_invalid(self):
        node = CgroupNode(name="test", path="/test")
        with pytest.raises(CgroupsDelegationError):
            node.set_subtree_control({CgroupControllerType.CPU})

    def test_enable_subtree_controller(self):
        node = CgroupNode(
            name="test", path="/test",
            controllers={CgroupControllerType.IO},
        )
        node.enable_subtree_controller(CgroupControllerType.IO)
        assert CgroupControllerType.IO in node.subtree_control

    def test_disable_subtree_controller(self):
        node = CgroupNode(
            name="test", path="/test",
            controllers={CgroupControllerType.IO},
        )
        node.enable_subtree_controller(CgroupControllerType.IO)
        node.disable_subtree_controller(CgroupControllerType.IO)
        assert CgroupControllerType.IO not in node.subtree_control

    def test_recursive_process_count(self):
        root = CgroupNode(name="root", path="/")
        child = CgroupNode(name="child", path="/child", parent=root)
        root.add_child(child)
        root.attach_process(1)
        child.attach_process(2)
        child.attach_process(3)
        assert root.get_recursive_process_count() == 3

    def test_recursive_memory_usage(self):
        root = CgroupNode(
            name="root", path="/",
            controllers={CgroupControllerType.MEMORY},
        )
        child = CgroupNode(
            name="child", path="/child", parent=root,
            controllers={CgroupControllerType.MEMORY},
        )
        root.add_child(child)
        root_mem = root.get_controller(CgroupControllerType.MEMORY)
        child_mem = child.get_controller(CgroupControllerType.MEMORY)
        root_mem.charge(1, 100, "rss")
        child_mem.charge(2, 200, "rss")
        assert root.get_recursive_memory_usage() == 300

    def test_mark_draining(self):
        node = CgroupNode(name="test", path="/test")
        node.mark_draining()
        assert node.state == CgroupState.DRAINING

    def test_mark_removed(self):
        node = CgroupNode(name="test", path="/test")
        node.mark_removed()
        assert node.state == CgroupState.REMOVED

    def test_controller_types_property(self):
        node = CgroupNode(
            name="test", path="/test",
            controllers={CgroupControllerType.CPU, CgroupControllerType.PIDS},
        )
        types = node.controller_types
        assert CgroupControllerType.CPU in types
        assert CgroupControllerType.PIDS in types

    def test_created_at(self):
        before = time.time()
        node = CgroupNode(name="test", path="/test")
        after = time.time()
        assert before <= node.created_at <= after

    def test_to_dict(self):
        node = CgroupNode(
            name="test", path="/test",
            controllers={CgroupControllerType.CPU},
        )
        d = node.to_dict()
        assert d["name"] == "test"
        assert d["path"] == "/test"
        assert "cpu" in d["controllers"]

    def test_repr(self):
        node = CgroupNode(name="test", path="/test")
        r = repr(node)
        assert "CgroupNode" in r

    def test_oom_killer_property(self):
        node = CgroupNode(name="test", path="/test")
        assert isinstance(node.oom_killer, OOMKiller)

    def test_all_controllers(self):
        node = CgroupNode(
            name="test", path="/test",
            controllers=set(CgroupControllerType),
        )
        assert node.has_controller(CgroupControllerType.CPU)
        assert node.has_controller(CgroupControllerType.MEMORY)
        assert node.has_controller(CgroupControllerType.IO)
        assert node.has_controller(CgroupControllerType.PIDS)


# ============================================================
# CgroupHierarchy Tests
# ============================================================


class TestCgroupHierarchy:
    """Validate cgroup hierarchy tree operations."""

    def test_root_exists(self):
        h = CgroupHierarchy()
        assert h.root is not None
        assert h.root.path == ROOT_CGROUP_PATH

    def test_create_child(self):
        h = CgroupHierarchy()
        node = h.create("/fizzkube")
        assert node.name == "fizzkube"
        assert node.path == "/fizzkube"
        assert node.parent == h.root

    def test_create_nested(self):
        h = CgroupHierarchy()
        h.create("/fizzkube")
        h.create("/fizzkube/pod-abc")
        node = h.get("/fizzkube/pod-abc")
        assert node is not None
        assert node.name == "pod-abc"

    def test_create_duplicate(self):
        h = CgroupHierarchy()
        h.create("/fizzkube")
        with pytest.raises(CgroupCreationError):
            h.create("/fizzkube")

    def test_create_root(self):
        h = CgroupHierarchy()
        with pytest.raises(CgroupCreationError):
            h.create("/")

    def test_create_missing_parent(self):
        h = CgroupHierarchy()
        with pytest.raises(CgroupCreationError):
            h.create("/nonexistent/child")

    def test_remove(self):
        h = CgroupHierarchy()
        h.create("/test")
        h.remove("/test")
        assert h.get("/test") is None

    def test_remove_root(self):
        h = CgroupHierarchy()
        with pytest.raises(CgroupRemovalError):
            h.remove("/")

    def test_remove_with_children(self):
        h = CgroupHierarchy()
        h.create("/parent")
        h.create("/parent/child")
        with pytest.raises(CgroupRemovalError):
            h.remove("/parent")

    def test_remove_with_processes(self):
        h = CgroupHierarchy()
        h.create("/test")
        h.attach(1, "/test")
        with pytest.raises(CgroupRemovalError):
            h.remove("/test")

    def test_remove_nonexistent(self):
        h = CgroupHierarchy()
        with pytest.raises(CgroupHierarchyError):
            h.remove("/nonexistent")

    def test_get_existing(self):
        h = CgroupHierarchy()
        h.create("/test")
        node = h.get("/test")
        assert node is not None

    def test_get_nonexistent(self):
        h = CgroupHierarchy()
        assert h.get("/nonexistent") is None

    def test_exists(self):
        h = CgroupHierarchy()
        h.create("/test")
        assert h.exists("/test") is True
        assert h.exists("/nonexistent") is False

    def test_attach_process(self):
        h = CgroupHierarchy()
        h.create("/test")
        h.attach(1, "/test")
        node = h.get("/test")
        assert 1 in node.processes

    def test_attach_nonexistent(self):
        h = CgroupHierarchy()
        with pytest.raises(CgroupAttachError):
            h.attach(1, "/nonexistent")

    def test_attach_moves_from_previous(self):
        h = CgroupHierarchy()
        h.create("/a")
        h.create("/b")
        h.attach(1, "/a")
        h.attach(1, "/b")
        a = h.get("/a")
        b = h.get("/b")
        assert 1 not in a.processes
        assert 1 in b.processes

    def test_migrate(self):
        h = CgroupHierarchy()
        h.create("/from")
        h.create("/to")
        h.attach(1, "/from")
        h.migrate(1, "/from", "/to")
        assert 1 not in h.get("/from").processes
        assert 1 in h.get("/to").processes

    def test_migrate_nonexistent_source(self):
        h = CgroupHierarchy()
        h.create("/to")
        with pytest.raises(CgroupMigrationError):
            h.migrate(1, "/nonexistent", "/to")

    def test_migrate_nonexistent_dest(self):
        h = CgroupHierarchy()
        h.create("/from")
        h.attach(1, "/from")
        with pytest.raises(CgroupMigrationError):
            h.migrate(1, "/from", "/nonexistent")

    def test_migrate_process_not_in_source(self):
        h = CgroupHierarchy()
        h.create("/from")
        h.create("/to")
        with pytest.raises(CgroupMigrationError):
            h.migrate(999, "/from", "/to")

    def test_walk(self):
        h = CgroupHierarchy()
        h.create("/a")
        h.create("/a/b")
        h.create("/a/c")
        nodes = h.walk()
        assert len(nodes) == 4  # root, a, b, c

    def test_walk_subtree(self):
        h = CgroupHierarchy()
        h.create("/a")
        h.create("/a/b")
        h.create("/c")
        nodes = h.walk("/a")
        assert len(nodes) == 2  # a, b

    def test_walk_nonexistent(self):
        h = CgroupHierarchy()
        assert h.walk("/nope") == []

    def test_get_all_paths(self):
        h = CgroupHierarchy()
        h.create("/a")
        h.create("/b")
        paths = h.get_all_paths()
        assert "/" in paths
        assert "/a" in paths
        assert "/b" in paths

    def test_find_process(self):
        h = CgroupHierarchy()
        h.create("/test")
        h.attach(42, "/test")
        assert h.find_process(42) == "/test"

    def test_find_process_not_found(self):
        h = CgroupHierarchy()
        assert h.find_process(999) is None

    def test_render_tree(self):
        h = CgroupHierarchy()
        h.create("/fizzkube")
        tree = h.render_tree()
        assert "fizzkube" in tree
        assert ROOT_CGROUP_PATH in tree

    def test_render_tree_nonexistent(self):
        h = CgroupHierarchy()
        result = h.render_tree("/nope")
        assert "not found" in result

    def test_total_created(self):
        h = CgroupHierarchy()
        h.create("/a")
        h.create("/b")
        assert h.total_created == 3  # root + a + b

    def test_total_removed(self):
        h = CgroupHierarchy()
        h.create("/a")
        h.remove("/a")
        assert h.total_removed == 1

    def test_active_count(self):
        h = CgroupHierarchy()
        h.create("/a")
        h.create("/b")
        assert h.active_count == 3

    def test_get_statistics(self):
        h = CgroupHierarchy()
        stats = h.get_statistics()
        assert "total_created" in stats
        assert "active_count" in stats

    def test_normalize_path(self):
        h = CgroupHierarchy()
        h.create("/test")
        assert h.get("test") is not None
        assert h.get("/test/") is not None

    def test_depth_limit(self):
        h = CgroupHierarchy()
        path = ""
        for i in range(MAX_CGROUP_DEPTH + 1):
            path += f"/d{i}"
            if i >= MAX_CGROUP_DEPTH - 1:
                with pytest.raises(CgroupHierarchyError):
                    h.create(path)
                break
            else:
                h.create(path)

    def test_controller_inheritance(self):
        h = CgroupHierarchy()
        child = h.create("/child")
        # Child should inherit from root's subtree_control
        assert child.has_controller(CgroupControllerType.CPU)
        assert child.has_controller(CgroupControllerType.MEMORY)

    def test_get_all_processes(self):
        h = CgroupHierarchy()
        h.create("/a")
        h.attach(1, "/a")
        h.attach(2, "/a")
        procs = h.get_all_processes()
        assert "/a" in procs
        assert len(procs["/a"]) == 2

    def test_repr(self):
        h = CgroupHierarchy()
        r = repr(h)
        assert "CgroupHierarchy" in r

    def test_event_bus_create(self):
        bus = MagicMock()
        h = CgroupHierarchy(event_bus=bus)
        h.create("/test")
        assert bus.publish.called

    def test_event_bus_remove(self):
        bus = MagicMock()
        h = CgroupHierarchy(event_bus=bus)
        h.create("/test")
        bus.reset_mock()
        h.remove("/test")
        assert bus.publish.called

    def test_create_draining_parent(self):
        h = CgroupHierarchy()
        node = h.create("/parent")
        node.mark_draining()
        with pytest.raises(CgroupCreationError):
            h.create("/parent/child")

    def test_migrate_inactive_dest(self):
        h = CgroupHierarchy()
        h.create("/from")
        h.create("/to")
        h.attach(1, "/from")
        to_node = h.get("/to")
        to_node.mark_draining()
        with pytest.raises(CgroupMigrationError):
            h.migrate(1, "/from", "/to")


# ============================================================
# CgroupManager Tests
# ============================================================


class TestCgroupManager:
    """Validate CgroupManager singleton and API."""

    def test_singleton(self):
        m1 = CgroupManager()
        m2 = CgroupManager()
        assert m1 is m2

    def test_create_cgroup(self):
        m = CgroupManager()
        node = m.create_cgroup("/test")
        assert node is not None
        assert node.path == "/test"

    def test_remove_cgroup(self):
        m = CgroupManager()
        m.create_cgroup("/test")
        m.remove_cgroup("/test")
        assert m.get_cgroup("/test") is None

    def test_get_cgroup(self):
        m = CgroupManager()
        m.create_cgroup("/test")
        assert m.get_cgroup("/test") is not None
        assert m.get_cgroup("/nonexistent") is None

    def test_attach_process(self):
        m = CgroupManager()
        m.create_cgroup("/test")
        m.attach_process(1, "/test")
        assert 1 in m.get_cgroup("/test").processes

    def test_migrate_process(self):
        m = CgroupManager()
        m.create_cgroup("/a")
        m.create_cgroup("/b")
        m.attach_process(1, "/a")
        m.migrate_process(1, "/a", "/b")
        assert 1 in m.get_cgroup("/b").processes

    def test_set_cpu_weight(self):
        m = CgroupManager()
        m.create_cgroup("/test")
        m.set_cpu_weight("/test", 500)
        cpu = m.get_cgroup("/test").get_controller(CgroupControllerType.CPU)
        assert cpu.weight == 500

    def test_set_cpu_weight_nonexistent(self):
        m = CgroupManager()
        with pytest.raises(CgroupManagerError):
            m.set_cpu_weight("/nope", 100)

    def test_set_cpu_bandwidth(self):
        m = CgroupManager()
        m.create_cgroup("/test")
        m.set_cpu_bandwidth("/test", 50000)
        cpu = m.get_cgroup("/test").get_controller(CgroupControllerType.CPU)
        assert cpu.quota == 50000

    def test_set_memory_max(self):
        m = CgroupManager()
        m.create_cgroup("/test")
        m.set_memory_max("/test", 1048576)
        mem = m.get_cgroup("/test").get_controller(CgroupControllerType.MEMORY)
        assert mem.config.max == 1048576

    def test_set_memory_max_nonexistent(self):
        m = CgroupManager()
        with pytest.raises(CgroupManagerError):
            m.set_memory_max("/nope", 100)

    def test_set_pids_max(self):
        m = CgroupManager()
        m.create_cgroup("/test")
        m.set_pids_max("/test", 100)
        pids = m.get_cgroup("/test").get_controller(CgroupControllerType.PIDS)
        assert pids.limit == 100

    def test_set_pids_max_nonexistent(self):
        m = CgroupManager()
        with pytest.raises(CgroupManagerError):
            m.set_pids_max("/nope", 100)

    def test_charge_cpu(self):
        m = CgroupManager()
        result = m.charge_cpu("/", 1000)
        assert result is True

    def test_charge_cpu_nonexistent(self):
        m = CgroupManager()
        result = m.charge_cpu("/nonexistent", 1000)
        assert result is True  # No-op

    def test_charge_memory(self):
        m = CgroupManager()
        result = m.charge_memory("/", 1, 1024)
        assert result is True

    def test_charge_io_read(self):
        m = CgroupManager()
        result = m.charge_io_read("/", "sda", 4096)
        assert result is True

    def test_charge_io_write(self):
        m = CgroupManager()
        result = m.charge_io_write("/", "sda", 4096)
        assert result is True

    def test_find_process_cgroup(self):
        m = CgroupManager()
        m.create_cgroup("/test")
        m.attach_process(42, "/test")
        assert m.find_process_cgroup(42) == "/test"

    def test_render_tree(self):
        m = CgroupManager()
        tree = m.render_tree()
        assert "/" in tree

    def test_get_statistics(self):
        m = CgroupManager()
        stats = m.get_statistics()
        assert "total_charges" in stats

    def test_root_property(self):
        m = CgroupManager()
        assert m.root.path == ROOT_CGROUP_PATH

    def test_hierarchy_property(self):
        m = CgroupManager()
        assert isinstance(m.hierarchy, CgroupHierarchy)

    def test_oom_policy_property(self):
        m = CgroupManager(oom_policy=OOMPolicy.KILL_OLDEST)
        assert m.oom_policy == OOMPolicy.KILL_OLDEST

    def test_to_dict(self):
        m = CgroupManager()
        d = m.to_dict()
        assert "oom_policy" in d

    def test_repr(self):
        m = CgroupManager()
        r = repr(m)
        assert "CgroupManager" in r


# ============================================================
# ResourceAccountant Tests
# ============================================================


class TestResourceAccountant:
    """Validate resource report generation and HPA metrics."""

    def test_generate_report(self):
        m = CgroupManager()
        a = ResourceAccountant(m)
        report = a.generate_report("/")
        assert report.cgroup_path == "/"
        assert report.timestamp > 0

    def test_generate_report_nonexistent(self):
        m = CgroupManager()
        a = ResourceAccountant(m)
        with pytest.raises(ResourceAccountantError):
            a.generate_report("/nonexistent")

    def test_report_cpu_stats(self):
        m = CgroupManager()
        m.charge_cpu("/", 5000)
        a = ResourceAccountant(m)
        report = a.generate_report("/")
        assert report.cpu_stats.usage_usec == 5000

    def test_report_memory_stats(self):
        m = CgroupManager()
        m.charge_memory("/", 1, 1024)
        a = ResourceAccountant(m)
        report = a.generate_report("/")
        assert report.memory_stats.current == 1024

    def test_generate_all_reports(self):
        m = CgroupManager()
        m.create_cgroup("/test")
        a = ResourceAccountant(m)
        reports = a.generate_all_reports()
        assert "/" in reports
        assert "/test" in reports

    def test_get_hpa_metrics(self):
        m = CgroupManager()
        a = ResourceAccountant(m)
        metrics = a.get_hpa_metrics("/")
        assert "cpu_utilization_pct" in metrics
        assert "memory_utilization_pct" in metrics

    def test_get_top_by_cpu(self):
        m = CgroupManager()
        a = ResourceAccountant(m)
        top = a.get_top_by_cpu()
        assert isinstance(top, list)

    def test_get_top_by_memory(self):
        m = CgroupManager()
        a = ResourceAccountant(m)
        top = a.get_top_by_memory()
        assert isinstance(top, list)

    def test_report_count(self):
        m = CgroupManager()
        a = ResourceAccountant(m)
        a.generate_report("/")
        a.generate_report("/")
        assert a.report_count == 2

    def test_to_dict(self):
        m = CgroupManager()
        a = ResourceAccountant(m)
        d = a.to_dict()
        assert "report_count" in d


# ============================================================
# FizzCgroupDashboard Tests
# ============================================================


class TestFizzCgroupDashboard:
    """Validate ASCII dashboard rendering."""

    def test_render(self):
        m = CgroupManager()
        a = ResourceAccountant(m)
        output = FizzCgroupDashboard.render(m, a)
        assert "FIZZCGROUP" in output
        assert "Active Cgroups" in output

    def test_render_custom_width(self):
        m = CgroupManager()
        a = ResourceAccountant(m)
        output = FizzCgroupDashboard.render(m, a, width=80)
        assert len(output) > 0

    def test_render_with_cgroups(self):
        m = CgroupManager()
        m.create_cgroup("/fizzkube")
        m.create_cgroup("/fizzkube/pod-1")
        a = ResourceAccountant(m)
        output = FizzCgroupDashboard.render(m, a)
        assert "fizzkube" in output

    def test_render_top(self):
        m = CgroupManager()
        a = ResourceAccountant(m)
        output = FizzCgroupDashboard.render_top(a)
        assert "FIZZCGROUP TOP" in output

    def test_render_top_by_memory(self):
        m = CgroupManager()
        a = ResourceAccountant(m)
        output = FizzCgroupDashboard.render_top(a, sort_by="memory")
        assert "FIZZCGROUP TOP" in output


# ============================================================
# FizzCgroupMiddleware Tests
# ============================================================


class TestFizzCgroupMiddleware:
    """Validate middleware integration and priority."""

    def _make_middleware(self, **kwargs):
        m = CgroupManager(**kwargs.pop("manager_kwargs", {}))
        a = ResourceAccountant(m)
        return FizzCgroupMiddleware(m, a, **kwargs)

    def test_get_name(self):
        mw = self._make_middleware()
        assert mw.get_name() == "FizzCgroupMiddleware"

    def test_get_priority(self):
        mw = self._make_middleware()
        assert mw.get_priority() == 107

    def test_process(self):
        mw = self._make_middleware()
        ctx = ProcessingContext(number=5, session_id="test", results=[], metadata={})
        result = FizzBuzzResult(number=5, output="Buzz")
        result.metadata = {}

        def next_handler(c):
            return result

        output = mw.process(ctx, next_handler)
        assert "fizzcgroup_active_cgroups" in output.metadata
        assert mw.evaluations_processed == 1

    def test_process_charges_cpu(self):
        mw = self._make_middleware()
        ctx = ProcessingContext(number=3, session_id="test", results=[], metadata={})
        result = FizzBuzzResult(number=3, output="Fizz")
        result.metadata = {}

        def next_handler(c):
            return result

        mw.process(ctx, next_handler)
        stats = mw.manager.get_statistics()
        assert stats["total_charges"] > 0

    def test_process_error(self):
        mw = self._make_middleware()
        ctx = ProcessingContext(number=1, session_id="test", results=[], metadata={})

        def bad_handler(c):
            raise RuntimeError("test error")

        with pytest.raises(CgroupMiddlewareError):
            mw.process(ctx, bad_handler)

    def test_manager_property(self):
        mw = self._make_middleware()
        assert isinstance(mw.manager, CgroupManager)

    def test_accountant_property(self):
        mw = self._make_middleware()
        assert isinstance(mw.accountant, ResourceAccountant)

    def test_render_dashboard(self):
        mw = self._make_middleware()
        output = mw.render_dashboard()
        assert "FIZZCGROUP" in output

    def test_render_tree(self):
        mw = self._make_middleware()
        output = mw.render_tree()
        assert "/" in output

    def test_render_stats(self):
        mw = self._make_middleware()
        output = mw.render_stats("/")
        assert "Resource Statistics" in output

    def test_render_stats_nonexistent(self):
        mw = self._make_middleware()
        output = mw.render_stats("/nonexistent")
        assert "Error" in output

    def test_render_top(self):
        mw = self._make_middleware()
        output = mw.render_top()
        assert "FIZZCGROUP TOP" in output

    def test_with_event_bus(self):
        bus = MagicMock()
        mw = self._make_middleware(event_bus=bus)
        ctx = ProcessingContext(number=1, session_id="test", results=[], metadata={})
        result = FizzBuzzResult(number=1, output="1")
        result.metadata = {}

        def next_handler(c):
            return result

        mw.process(ctx, next_handler)
        assert bus.publish.called


# ============================================================
# Factory Function Tests
# ============================================================


class TestCreateFizzcgroupSubsystem:
    """Validate the factory function."""

    def test_returns_tuple(self):
        result = create_fizzcgroup_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_returns_manager(self):
        manager, _ = create_fizzcgroup_subsystem()
        assert isinstance(manager, CgroupManager)

    def test_returns_middleware(self):
        _, middleware = create_fizzcgroup_subsystem()
        assert isinstance(middleware, FizzCgroupMiddleware)

    def test_custom_oom_policy(self):
        manager, _ = create_fizzcgroup_subsystem(oom_policy="kill_oldest")
        assert manager.oom_policy == OOMPolicy.KILL_OLDEST

    def test_invalid_oom_policy_defaults(self):
        manager, _ = create_fizzcgroup_subsystem(oom_policy="invalid")
        assert manager.oom_policy == OOMPolicy.KILL_LARGEST

    def test_with_event_bus(self):
        bus = MagicMock()
        _, middleware = create_fizzcgroup_subsystem(event_bus=bus)
        assert middleware is not None

    def test_dashboard_width(self):
        _, middleware = create_fizzcgroup_subsystem(dashboard_width=100)
        assert middleware._dashboard_width == 100


# ============================================================
# Exception Tests
# ============================================================


class TestExceptions:
    """Validate all 19 cgroup exception classes."""

    def test_cgroup_error(self):
        e = CgroupError("test reason")
        assert "test reason" in str(e)
        assert e.error_code == "EFP-CG00"

    def test_cgroup_creation_error(self):
        e = CgroupCreationError("create fail")
        assert "create fail" in str(e)
        assert e.error_code == "EFP-CG01"

    def test_cgroup_removal_error(self):
        e = CgroupRemovalError("remove fail")
        assert e.error_code == "EFP-CG02"

    def test_cgroup_attach_error(self):
        e = CgroupAttachError("attach fail")
        assert e.error_code == "EFP-CG03"

    def test_cgroup_migration_error(self):
        e = CgroupMigrationError("migrate fail")
        assert e.error_code == "EFP-CG04"

    def test_cgroup_hierarchy_error(self):
        e = CgroupHierarchyError("hierarchy fail")
        assert e.error_code == "EFP-CG05"

    def test_cgroup_delegation_error(self):
        e = CgroupDelegationError("unit1", "cpu", "delegation fail")
        assert e.error_code == "EFP-SYD18"

    def test_cgroup_controller_error(self):
        e = CgroupControllerError("controller fail")
        assert e.error_code == "EFP-CG07"

    def test_cpu_controller_error(self):
        e = CPUControllerError("cpu fail")
        assert e.error_code == "EFP-CG08"

    def test_memory_controller_error(self):
        e = MemoryControllerError("mem fail")
        assert e.error_code == "EFP-CG09"

    def test_io_controller_error(self):
        e = IOControllerError("io fail")
        assert e.error_code == "EFP-CG10"

    def test_pids_controller_error(self):
        e = PIDsControllerError("pids fail")
        assert e.error_code == "EFP-CG11"

    def test_oom_killer_error(self):
        e = OOMKillerError("oom fail")
        assert e.error_code == "EFP-CG12"

    def test_resource_accountant_error(self):
        e = ResourceAccountantError("accountant fail")
        assert e.error_code == "EFP-CG13"

    def test_cgroup_quota_exceeded_error(self):
        e = CgroupQuotaExceededError("quota exceeded")
        assert e.error_code == "EFP-CG14"

    def test_cgroup_throttle_error(self):
        e = CgroupThrottleError("throttle fail")
        assert e.error_code == "EFP-CG15"

    def test_cgroup_manager_error(self):
        e = CgroupManagerError("manager fail")
        assert e.error_code == "EFP-CG16"

    def test_cgroup_dashboard_error(self):
        e = CgroupDashboardError("dashboard fail")
        assert e.error_code == "EFP-CG17"

    def test_cgroup_middleware_error(self):
        e = CgroupMiddlewareError(evaluation_number=42, reason="middleware fail")
        assert e.error_code == "EFP-CG18"
        assert e.evaluation_number == 42

    def test_all_inherit_from_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        cgroup_exceptions = [
            CgroupError("x"),
            CgroupCreationError("x"),
            CgroupRemovalError("x"),
            CgroupAttachError("x"),
            CgroupMigrationError("x"),
            CgroupHierarchyError("x"),
            CgroupControllerError("x"),
            CPUControllerError("x"),
            MemoryControllerError("x"),
            IOControllerError("x"),
            PIDsControllerError("x"),
            OOMKillerError("x"),
            ResourceAccountantError("x"),
            CgroupQuotaExceededError("x"),
            CgroupThrottleError("x"),
            CgroupManagerError("x"),
            CgroupDashboardError("x"),
            CgroupMiddlewareError(1, "x"),
        ]
        for exc in cgroup_exceptions:
            assert isinstance(exc, FizzBuzzError)
            assert isinstance(exc, CgroupError)
        # CgroupDelegationError now inherits from SystemdError
        delegation_err = CgroupDelegationError("x", "cpu", "reason")
        assert isinstance(delegation_err, FizzBuzzError)

    def test_all_have_context(self):
        e = CgroupError("test reason")
        assert e.context == {"reason": "test reason"}


# ============================================================
# Singleton Reset Tests
# ============================================================


class TestSingletonReset:
    """Validate singleton reset between tests."""

    def test_manager_fresh_after_reset(self):
        m1 = CgroupManager()
        m1.create_cgroup("/test_reset")
        _CgroupManagerMeta.reset()
        m2 = CgroupManager()
        assert m2.get_cgroup("/test_reset") is None

    def test_reset_creates_new_instance(self):
        m1 = CgroupManager()
        _CgroupManagerMeta.reset()
        m2 = CgroupManager()
        assert m1 is not m2


# ============================================================
# Integration Tests
# ============================================================


class TestIntegration:
    """End-to-end integration tests combining multiple components."""

    def test_full_lifecycle(self):
        """Create cgroup, attach processes, charge resources, generate report."""
        manager, middleware = create_fizzcgroup_subsystem()
        node = manager.create_cgroup("/fizzkube")
        pod = manager.create_cgroup("/fizzkube/pod-1")
        manager.attach_process(1, "/fizzkube/pod-1")
        manager.charge_cpu("/fizzkube/pod-1", 10000)
        manager.charge_memory("/fizzkube/pod-1", 1, 2048, "rss")

        report = middleware.accountant.generate_report("/fizzkube/pod-1")
        assert report.cpu_stats.usage_usec == 10000
        assert report.memory_stats.rss == 2048

    def test_oom_kill_lifecycle(self):
        """Trigger OOM kill through memory limit."""
        manager = CgroupManager()
        node = manager.create_cgroup("/test")
        mem = node.get_controller(CgroupControllerType.MEMORY)
        mem.set_max(1000)
        node.attach_process(1)
        node.attach_process(2)
        mem.charge(1, 400, "rss")
        mem.charge(2, 500, "rss")

        # This should trigger OOM
        result = mem.charge(1, 200, "rss")
        assert result is False

    def test_hierarchy_with_controllers(self):
        """Verify controller inheritance through hierarchy."""
        manager = CgroupManager()
        manager.create_cgroup("/parent")
        manager.create_cgroup("/parent/child")
        child = manager.get_cgroup("/parent/child")
        assert child.has_controller(CgroupControllerType.CPU)
        assert child.has_controller(CgroupControllerType.MEMORY)
        assert child.has_controller(CgroupControllerType.IO)
        assert child.has_controller(CgroupControllerType.PIDS)

    def test_migration_preserves_memory(self):
        """Verify memory charges are migrated between cgroups."""
        manager = CgroupManager()
        manager.create_cgroup("/a")
        manager.create_cgroup("/b")
        manager.attach_process(1, "/a")
        manager.charge_memory("/a", 1, 512, "rss")

        manager.migrate_process(1, "/a", "/b")
        b_mem = manager.get_cgroup("/b").get_controller(CgroupControllerType.MEMORY)
        assert b_mem.get_process_charge(1) == 512

    def test_dashboard_after_activity(self):
        """Render dashboard after charging resources."""
        manager, middleware = create_fizzcgroup_subsystem()
        manager.create_cgroup("/fizzkube")
        manager.attach_process(1, "/fizzkube")
        manager.charge_cpu("/fizzkube", 5000)
        output = middleware.render_dashboard()
        assert "FIZZCGROUP" in output

    def test_middleware_pipeline(self):
        """Process multiple evaluations through middleware."""
        manager, middleware = create_fizzcgroup_subsystem()

        for i in range(10):
            ctx = ProcessingContext(number=i + 1, session_id="test", results=[], metadata={})
            result = FizzBuzzResult(number=i + 1, output=str(i + 1))
            result.metadata = {}

            def handler(c, r=result):
                return r

            middleware.process(ctx, handler)

        assert middleware.evaluations_processed == 10

    def test_top_view(self):
        """Render top view with multiple cgroups."""
        manager, middleware = create_fizzcgroup_subsystem()
        manager.create_cgroup("/a")
        manager.create_cgroup("/b")
        manager.charge_cpu("/a", 10000)
        manager.charge_cpu("/b", 5000)
        output = middleware.render_top()
        assert "FIZZCGROUP TOP" in output

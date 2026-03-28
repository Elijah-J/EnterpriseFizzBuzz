"""
Enterprise FizzBuzz Platform - FizzSmartNIC Offload Engine Test Suite

Comprehensive tests for the Smart NIC offload engine, covering offload
program compilation and execution, flow table management, hardware
checksum offload, packet classification, NIC queue operations, FizzBuzz
evaluation via NIC offload, dashboard rendering, and middleware integration.

The FizzSmartNIC subsystem enables wire-speed FizzBuzz evaluation by
executing classification logic directly on the network adapter. These
tests verify correct offload program behavior, flow matching, and
hardware acceleration.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzsmartnic import (
    DEFAULT_RING_SIZE,
    FIZZSMARTNIC_VERSION,
    MAX_FLOW_RULES,
    MIDDLEWARE_PRIORITY,
    ActionType,
    ChecksumEngine,
    ChecksumResult,
    ChecksumType,
    FlowRule,
    FlowTable,
    HWAccelerator,
    InstructionType,
    MatchType,
    NICQueue,
    NICState,
    OffloadEngine,
    OffloadInstruction,
    OffloadProgram,
    PacketClassifier,
    QueueDirection,
    SmartNIC,
    SmartNICDashboard,
    SmartNICMiddleware,
    create_fizzsmartnic_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    SmartNICError,
    SmartNICProgramError,
    SmartNICFlowTableError,
    SmartNICAccelerationError,
    SmartNICClassificationError,
    SmartNICChecksumError,
    SmartNICQueueError,
    SmartNICFirmwareError,
)


# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    """Verify SmartNIC constants match documented specifications."""

    def test_version(self):
        assert FIZZSMARTNIC_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 255

    def test_max_flow_rules(self):
        assert MAX_FLOW_RULES == 8192

    def test_default_ring_size(self):
        assert DEFAULT_RING_SIZE == 512


# =========================================================================
# Offload Program
# =========================================================================


class TestOffloadProgram:
    """Verify offload program compilation and instruction count."""

    def test_add_instruction(self):
        prog = OffloadProgram(program_id=1, name="test")
        prog.add_instruction(OffloadInstruction(InstructionType.MATCH))
        prog.add_instruction(OffloadInstruction(InstructionType.CLASSIFY))
        assert prog.instruction_count() == 2

    def test_initial_not_loaded(self):
        prog = OffloadProgram(program_id=1, name="test")
        assert prog.loaded is False


# =========================================================================
# Offload Engine
# =========================================================================


class TestOffloadEngine:
    """Verify offload engine program management and execution."""

    def test_compile_program(self):
        engine = OffloadEngine()
        instructions = [OffloadInstruction(InstructionType.CLASSIFY)]
        prog = engine.compile_program("fizzbuzz", instructions)
        assert prog.program_id >= 1
        assert engine.program_count == 1

    def test_load_program(self):
        engine = OffloadEngine()
        instructions = [OffloadInstruction(InstructionType.CLASSIFY)]
        prog = engine.compile_program("fizzbuzz", instructions)
        assert engine.load_program(prog.program_id) is True
        assert engine.active_program is not None

    def test_execute_classify(self):
        engine = OffloadEngine()
        instructions = [OffloadInstruction(InstructionType.CLASSIFY)]
        prog = engine.compile_program("fizzbuzz", instructions)
        engine.load_program(prog.program_id)
        assert engine.execute({"number": 15}) == "FizzBuzz"
        assert engine.execute({"number": 3}) == "Fizz"
        assert engine.execute({"number": 5}) == "Buzz"
        assert engine.execute({"number": 7}) == "7"

    def test_execute_no_program(self):
        engine = OffloadEngine()
        assert engine.execute({"number": 1}) is None


# =========================================================================
# Flow Table
# =========================================================================


class TestFlowTable:
    """Verify hardware flow table operations."""

    def test_add_rule(self):
        ft = FlowTable()
        rule = ft.add_rule(MatchType.EXACT, {"src_ip": "10.0.0.1"})
        assert rule.rule_id >= 1
        assert ft.rule_count == 1

    def test_delete_rule(self):
        ft = FlowTable()
        rule = ft.add_rule(MatchType.EXACT, {"src_ip": "10.0.0.1"})
        assert ft.delete_rule(rule.rule_id) is True
        assert ft.rule_count == 0

    def test_lookup_match(self):
        ft = FlowTable()
        ft.add_rule(MatchType.EXACT, {"src_ip": "10.0.0.1"},
                     action=ActionType.FORWARD, priority=10)
        result = ft.lookup({"src_ip": "10.0.0.1"})
        assert result is not None
        assert result.action == ActionType.FORWARD

    def test_lookup_miss(self):
        ft = FlowTable()
        ft.add_rule(MatchType.EXACT, {"src_ip": "10.0.0.1"})
        assert ft.lookup({"src_ip": "10.0.0.2"}) is None

    def test_priority_ordering(self):
        ft = FlowTable()
        ft.add_rule(MatchType.EXACT, {"src_ip": "10.0.0.1"},
                     action=ActionType.DROP, priority=1)
        ft.add_rule(MatchType.EXACT, {"src_ip": "10.0.0.1"},
                     action=ActionType.FORWARD, priority=10)
        result = ft.lookup({"src_ip": "10.0.0.1"})
        assert result.action == ActionType.FORWARD


# =========================================================================
# Checksum Engine
# =========================================================================


class TestChecksumEngine:
    """Verify hardware checksum offload."""

    def test_compute_checksum(self):
        engine = ChecksumEngine()
        result = engine.compute(b"\x00\x01\x00\x02", ChecksumType.IPV4)
        assert isinstance(result.value, int)
        assert result.valid is True

    def test_verify_checksum(self):
        engine = ChecksumEngine()
        result = engine.compute(b"\x00\x01\x00\x02", ChecksumType.TCP)
        assert engine.verify(b"\x00\x01\x00\x02", result.value, ChecksumType.TCP) is True

    def test_computation_count(self):
        engine = ChecksumEngine()
        engine.compute(b"\x01", ChecksumType.IPV4)
        engine.compute(b"\x02", ChecksumType.TCP)
        assert engine.computation_count == 2


# =========================================================================
# Packet Classifier
# =========================================================================


class TestPacketClassifier:
    """Verify multi-field packet classification."""

    def test_classify_hit(self):
        ft = FlowTable()
        ft.add_rule(MatchType.EXACT, {"type": "fizzbuzz"}, priority=1)
        clf = PacketClassifier(ft)
        result = clf.classify({"type": "fizzbuzz"})
        assert result is not None

    def test_classify_miss(self):
        ft = FlowTable()
        clf = PacketClassifier(ft)
        assert clf.classify({"type": "unknown"}) is None
        assert clf.miss_count == 1

    def test_hit_ratio(self):
        ft = FlowTable()
        ft.add_rule(MatchType.EXACT, {"type": "fizz"}, priority=1)
        clf = PacketClassifier(ft)
        clf.classify({"type": "fizz"})  # hit
        clf.classify({"type": "buzz"})  # miss
        assert abs(clf.hit_ratio - 0.5) < 0.01


# =========================================================================
# NIC Queue
# =========================================================================


class TestNICQueue:
    """Verify hardware NIC queue operations."""

    def test_enqueue_dequeue(self):
        q = NICQueue(0, QueueDirection.TX)
        assert q.enqueue({"data": "fizz", "length": 64}) is True
        pkt = q.dequeue()
        assert pkt is not None
        assert pkt["data"] == "fizz"

    def test_queue_full_drops(self):
        q = NICQueue(0, QueueDirection.RX, ring_size=2)
        q.enqueue({"data": "a", "length": 64})
        q.enqueue({"data": "b", "length": 64})
        assert q.enqueue({"data": "c", "length": 64}) is False
        assert q.stats.drops == 1

    def test_stats_tracking(self):
        q = NICQueue(0, QueueDirection.TX)
        q.enqueue({"data": "fizz", "length": 100})
        assert q.stats.packets == 1
        assert q.stats.bytes == 100


# =========================================================================
# Smart NIC
# =========================================================================


class TestSmartNIC:
    """Verify complete Smart NIC operations."""

    def test_initial_state(self):
        nic = SmartNIC()
        assert nic.state == NICState.OFFLINE

    def test_bring_up(self):
        nic = SmartNIC()
        assert nic.bring_up() is True
        assert nic.state == NICState.ONLINE

    def test_default_program_loaded(self):
        nic = SmartNIC()
        assert nic.offload.active_program is not None
        assert nic.offload.active_program.name == "fizzbuzz_classify"

    def test_evaluate_fizzbuzz_fizz(self):
        nic = SmartNIC()
        assert nic.evaluate_fizzbuzz(3) == "Fizz"

    def test_evaluate_fizzbuzz_buzz(self):
        nic = SmartNIC()
        assert nic.evaluate_fizzbuzz(5) == "Buzz"

    def test_evaluate_fizzbuzz_fizzbuzz(self):
        nic = SmartNIC()
        assert nic.evaluate_fizzbuzz(15) == "FizzBuzz"

    def test_evaluate_fizzbuzz_number(self):
        nic = SmartNIC()
        assert nic.evaluate_fizzbuzz(7) == "7"

    def test_queue_count(self):
        nic = SmartNIC(num_queues=8)
        assert nic.queue_count == 16  # 8 TX + 8 RX

    def test_firmware_version(self):
        nic = SmartNIC()
        assert nic.firmware_version == "1.0.0"


# =========================================================================
# Dashboard
# =========================================================================


class TestSmartNICDashboard:
    """Verify ASCII dashboard rendering."""

    def test_render_produces_output(self):
        nic = SmartNIC()
        output = SmartNICDashboard.render(nic)
        assert "FizzSmartNIC" in output
        assert FIZZSMARTNIC_VERSION in output


# =========================================================================
# Middleware
# =========================================================================


class TestSmartNICMiddleware:
    """Verify pipeline middleware integration."""

    def test_middleware_sets_metadata(self):
        nic = SmartNIC()
        nic.bring_up()
        mw = SmartNICMiddleware(nic)

        @dataclass
        class Ctx:
            number: int
            session_id: str = "test"
            metadata: dict = None
            def __post_init__(self):
                if self.metadata is None:
                    self.metadata = {}

        ctx = Ctx(number=15)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["smartnic_classification"] == "FizzBuzz"
        assert result.metadata["smartnic_enabled"] is True

    def test_middleware_name(self):
        nic = SmartNIC()
        mw = SmartNICMiddleware(nic)
        assert mw.get_name() == "fizzsmartnic"

    def test_middleware_priority(self):
        nic = SmartNIC()
        mw = SmartNICMiddleware(nic)
        assert mw.get_priority() == 255


# =========================================================================
# Factory
# =========================================================================


class TestFactory:
    """Verify subsystem factory function."""

    def test_create_subsystem(self):
        nic, mw = create_fizzsmartnic_subsystem(num_queues=8)
        assert isinstance(nic, SmartNIC)
        assert isinstance(mw, SmartNICMiddleware)
        assert nic.state == NICState.ONLINE
        assert nic.queue_count == 16


# =========================================================================
# Exceptions
# =========================================================================


class TestExceptions:
    """Verify SmartNIC exception hierarchy."""

    def test_smartnic_error_base(self):
        err = SmartNICError("test")
        assert "test" in str(err)

    def test_smartnic_program_error(self):
        err = SmartNICProgramError("fizzbuzz_v2", "compilation failed")
        assert err.program_name == "fizzbuzz_v2"

    def test_smartnic_flow_table_error(self):
        err = SmartNICFlowTableError(1, "table full")
        assert err.table_id == 1

    def test_smartnic_checksum_error(self):
        err = SmartNICChecksumError("TCP", "invalid header")
        assert err.checksum_type == "TCP"

    def test_smartnic_firmware_error(self):
        err = SmartNICFirmwareError("2.0.0", "update failed")
        assert err.version == "2.0.0"

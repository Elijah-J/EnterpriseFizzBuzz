"""
Enterprise FizzBuzz Platform - FizzDAP Debug Adapter Protocol Test Suite

Comprehensive tests for the FizzDAP Debug Adapter Protocol Server,
because a debugger for a program that computes n%3 deserves its own
test suite with 50+ tests covering message framing, session state
machines, breakpoint management, stack frame synthesis, variable
inspection, expression evaluation, event emission, command dispatch,
and the all-important Debug Complexity Index.

If you're reading this test file wondering whether testing a debugger
for FizzBuzz is a productive use of engineering time, the answer is:
absolutely not, but the tests pass, and that's what matters.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzdap import (
    Breakpoint,
    BreakpointManager,
    DAPEventEmitter,
    DAPMessage,
    DAPSession,
    FizzDAPDashboard,
    FizzDAPServer,
    SessionState,
    StackFrame,
    StackFrameBuilder,
    VariableInspector,
)
from enterprise_fizzbuzz.domain.exceptions import (
    DAPBreakpointError,
    DAPError,
    DAPEvaluationError,
    DAPProtocolError,
    DAPSessionError,
)


# ============================================================
# DAPMessage Tests
# ============================================================


class TestDAPMessage:
    """Tests for DAP wire-format message encoding and decoding."""

    def test_encode_request(self):
        msg = DAPMessage(seq=1, msg_type="request", command="initialize",
                         body={"clientID": "test"})
        encoded = msg.encode()
        assert encoded.startswith("Content-Length:")
        assert "\r\n\r\n" in encoded
        body = encoded.split("\r\n\r\n", 1)[1]
        parsed = json.loads(body)
        assert parsed["type"] == "request"
        assert parsed["command"] == "initialize"
        assert parsed["arguments"]["clientID"] == "test"

    def test_encode_response(self):
        msg = DAPMessage(seq=2, msg_type="response", command="initialize",
                         request_seq=1, success=True, body={"key": "value"})
        encoded = msg.encode()
        body = encoded.split("\r\n\r\n", 1)[1]
        parsed = json.loads(body)
        assert parsed["type"] == "response"
        assert parsed["request_seq"] == 1
        assert parsed["success"] is True
        assert parsed["body"]["key"] == "value"

    def test_encode_event(self):
        msg = DAPMessage(seq=3, msg_type="event", command="stopped",
                         body={"reason": "breakpoint"})
        encoded = msg.encode()
        body = encoded.split("\r\n\r\n", 1)[1]
        parsed = json.loads(body)
        assert parsed["type"] == "event"
        assert parsed["event"] == "stopped"

    def test_content_length_correct(self):
        msg = DAPMessage(seq=1, msg_type="request", command="test")
        encoded = msg.encode()
        header, body = encoded.split("\r\n\r\n", 1)
        declared = int(header.split(":")[1].strip())
        actual = len(body.encode("utf-8"))
        assert declared == actual

    def test_decode_request(self):
        original = DAPMessage(seq=5, msg_type="request", command="stackTrace",
                              body={"threadId": 1})
        encoded = original.encode()
        decoded = DAPMessage.decode(encoded)
        assert decoded.msg_type == "request"
        assert decoded.command == "stackTrace"
        assert decoded.body["threadId"] == 1

    def test_decode_response(self):
        original = DAPMessage(seq=6, msg_type="response", command="evaluate",
                              request_seq=5, success=True,
                              body={"result": "42"})
        encoded = original.encode()
        decoded = DAPMessage.decode(encoded)
        assert decoded.msg_type == "response"
        assert decoded.success is True
        assert decoded.body["result"] == "42"

    def test_decode_event(self):
        original = DAPMessage(seq=7, msg_type="event", command="terminated",
                              body={"restart": False})
        encoded = original.encode()
        decoded = DAPMessage.decode(encoded)
        assert decoded.msg_type == "event"
        assert decoded.command == "terminated"

    def test_decode_missing_header_raises(self):
        with pytest.raises(DAPProtocolError, match="Content-Length"):
            DAPMessage.decode('{"type":"request"}')

    def test_decode_missing_separator_raises(self):
        with pytest.raises(DAPProtocolError, match="separator"):
            DAPMessage.decode("Content-Length: 5\n{}")

    def test_decode_invalid_content_length_raises(self):
        with pytest.raises(DAPProtocolError, match="not a valid integer"):
            DAPMessage.decode("Content-Length: abc\r\n\r\n{}")

    def test_decode_mismatched_length_raises(self):
        with pytest.raises(DAPProtocolError, match="Off by"):
            DAPMessage.decode('Content-Length: 999\r\n\r\n{"type":"request"}')

    def test_decode_invalid_json_raises(self):
        body = "not json at all"
        header = f"Content-Length: {len(body.encode('utf-8'))}"
        with pytest.raises(DAPProtocolError, match="Invalid JSON"):
            DAPMessage.decode(f"{header}\r\n\r\n{body}")

    def test_roundtrip_encoding(self):
        """Encode then decode should preserve the message semantics."""
        msg = DAPMessage(seq=42, msg_type="request", command="evaluate",
                         body={"expression": "n % 3"})
        decoded = DAPMessage.decode(msg.encode())
        assert decoded.seq == 42
        assert decoded.command == "evaluate"
        assert decoded.body["expression"] == "n % 3"


# ============================================================
# DAPSession Tests
# ============================================================


class TestDAPSession:
    """Tests for DAP session state machine."""

    def test_initial_state(self):
        session = DAPSession()
        assert session.state == SessionState.UNINITIALIZED
        assert session.is_active is True

    def test_valid_transition_uninitialized_to_initialized(self):
        session = DAPSession()
        session.transition_to(SessionState.INITIALIZED)
        assert session.state == SessionState.INITIALIZED

    def test_valid_transition_initialized_to_running(self):
        session = DAPSession()
        session.transition_to(SessionState.INITIALIZED)
        session.transition_to(SessionState.RUNNING)
        assert session.state == SessionState.RUNNING

    def test_valid_transition_running_to_stopped(self):
        session = DAPSession()
        session.transition_to(SessionState.INITIALIZED)
        session.transition_to(SessionState.RUNNING)
        session.transition_to(SessionState.STOPPED)
        assert session.state == SessionState.STOPPED

    def test_valid_transition_stopped_to_running(self):
        session = DAPSession()
        session.transition_to(SessionState.INITIALIZED)
        session.transition_to(SessionState.RUNNING)
        session.transition_to(SessionState.STOPPED)
        session.transition_to(SessionState.RUNNING)
        assert session.state == SessionState.RUNNING

    def test_valid_transition_to_terminated(self):
        session = DAPSession()
        session.transition_to(SessionState.INITIALIZED)
        session.transition_to(SessionState.TERMINATED)
        assert session.state == SessionState.TERMINATED
        assert session.is_active is False

    def test_invalid_transition_raises(self):
        session = DAPSession()
        with pytest.raises(DAPSessionError, match="UNINITIALIZED"):
            session.transition_to(SessionState.RUNNING)

    def test_terminated_is_terminal(self):
        session = DAPSession()
        session.transition_to(SessionState.INITIALIZED)
        session.transition_to(SessionState.TERMINATED)
        with pytest.raises(DAPSessionError):
            session.transition_to(SessionState.RUNNING)

    def test_session_id_is_set(self):
        session = DAPSession()
        assert len(session.session_id) == 8

    def test_capabilities_include_dap_features(self):
        session = DAPSession()
        assert session.capabilities["supportsConfigurationDoneRequest"] is True
        assert session.capabilities["supportsConditionalBreakpoints"] is True
        assert session.capabilities["supportsSetVariable"] is False

    def test_record_event(self):
        session = DAPSession()
        session.record_event("test_event", {"key": "value"})
        assert len(session.event_log) == 1
        assert session.event_log[0]["event"] == "test_event"

    def test_next_seq_increments(self):
        session = DAPSession()
        s1 = session.next_seq()
        s2 = session.next_seq()
        assert s2 == s1 + 1


# ============================================================
# BreakpointManager Tests
# ============================================================


class TestBreakpointManager:
    """Tests for breakpoint management."""

    def test_add_number_breakpoint(self):
        mgr = BreakpointManager()
        bp = mgr.add_number_breakpoint(15)
        assert bp.number == 15
        assert bp.id == 1
        assert bp.enabled is True

    def test_add_classification_breakpoint(self):
        mgr = BreakpointManager()
        bp = mgr.add_classification_breakpoint("FizzBuzz")
        assert bp.classification == "FizzBuzz"

    def test_add_classification_breakpoint_normalizes_case(self):
        mgr = BreakpointManager()
        bp = mgr.add_classification_breakpoint("FIZZ")
        assert bp.classification == "Fizz"

    def test_add_classification_breakpoint_invalid_raises(self):
        mgr = BreakpointManager()
        with pytest.raises(DAPBreakpointError, match="Unknown classification"):
            mgr.add_classification_breakpoint("Wuzz")

    def test_add_conditional_breakpoint(self):
        mgr = BreakpointManager()
        bp = mgr.add_conditional_breakpoint("n % 7 == 0")
        assert bp.condition == "n % 7 == 0"

    def test_remove_breakpoint(self):
        mgr = BreakpointManager()
        bp = mgr.add_number_breakpoint(15)
        assert mgr.remove_breakpoint(bp.id) is True
        assert len(mgr.breakpoints) == 0

    def test_remove_nonexistent_returns_false(self):
        mgr = BreakpointManager()
        assert mgr.remove_breakpoint(999) is False

    def test_clear_all(self):
        mgr = BreakpointManager()
        mgr.add_number_breakpoint(3)
        mgr.add_number_breakpoint(5)
        mgr.add_number_breakpoint(15)
        assert mgr.clear_all() == 3
        assert len(mgr.breakpoints) == 0

    def test_max_breakpoints_enforced(self):
        mgr = BreakpointManager(max_breakpoints=2)
        mgr.add_number_breakpoint(1)
        mgr.add_number_breakpoint(2)
        with pytest.raises(DAPBreakpointError, match="Maximum breakpoints"):
            mgr.add_number_breakpoint(3)

    def test_check_hit_number(self):
        mgr = BreakpointManager()
        mgr.add_number_breakpoint(15)
        hit = mgr.check_hit(15, "FizzBuzz")
        assert hit is not None
        assert hit.number == 15
        assert hit.hit_count == 1

    def test_check_hit_classification(self):
        mgr = BreakpointManager()
        mgr.add_classification_breakpoint("Fizz")
        hit = mgr.check_hit(3, "Fizz")
        assert hit is not None

    def test_check_hit_no_match(self):
        mgr = BreakpointManager()
        mgr.add_number_breakpoint(15)
        hit = mgr.check_hit(7, "7")
        assert hit is None

    def test_check_hit_conditional(self):
        mgr = BreakpointManager()
        mgr.add_conditional_breakpoint("n % 7 == 0")
        hit = mgr.check_hit(21, "Fizz")
        assert hit is not None

    def test_check_hit_disabled_breakpoint(self):
        mgr = BreakpointManager()
        bp = mgr.add_number_breakpoint(15)
        bp.enabled = False
        hit = mgr.check_hit(15, "FizzBuzz")
        assert hit is None

    def test_active_count(self):
        mgr = BreakpointManager()
        bp1 = mgr.add_number_breakpoint(3)
        bp2 = mgr.add_number_breakpoint(5)
        bp2.enabled = False
        assert mgr.active_count == 1

    def test_total_hits(self):
        mgr = BreakpointManager()
        mgr.add_number_breakpoint(3)
        mgr.check_hit(3, "Fizz")
        mgr.check_hit(3, "Fizz")
        assert mgr.total_hits == 2


# ============================================================
# StackFrameBuilder Tests
# ============================================================


class TestStackFrameBuilder:
    """Tests for synthetic stack frame generation."""

    def test_build_frames_empty_middleware(self):
        builder = StackFrameBuilder()
        frames = builder.build_frames([], current_number=15)
        assert len(frames) == 1  # Just the evaluation frame
        assert "evaluate(15)" in frames[0].name

    def test_build_frames_with_middleware(self):
        builder = StackFrameBuilder()
        frames = builder.build_frames(
            ["CacheMiddleware", "SLAMiddleware"], current_number=3
        )
        assert len(frames) == 3  # eval + 2 middleware
        assert "evaluate(3)" in frames[0].name
        assert "CacheMiddleware" in frames[1].name or "SLAMiddleware" in frames[1].name

    def test_build_frames_respects_max(self):
        builder = StackFrameBuilder(max_frames=3)
        frames = builder.build_frames(
            ["A", "B", "C", "D", "E"], current_number=1
        )
        # max_frames=3 means eval frame + up to 2 middleware
        assert len(frames) <= 3

    def test_build_frames_includes_source_location(self):
        builder = StackFrameBuilder(include_source_location=True)
        frames = builder.build_frames(["CacheMiddleware"], current_number=5)
        cache_frame = [f for f in frames if "CacheMiddleware" in f.name]
        assert len(cache_frame) == 1
        assert "cache.py" in cache_frame[0].source_file

    def test_build_frames_no_source_location(self):
        builder = StackFrameBuilder(include_source_location=False)
        frames = builder.build_frames(["CacheMiddleware"], current_number=5)
        cache_frame = [f for f in frames if "CacheMiddleware" in f.name]
        assert cache_frame[0].source_file == "<unknown>"

    def test_to_dap_response_format(self):
        builder = StackFrameBuilder()
        frames = builder.build_frames(["CacheMiddleware"], current_number=15)
        response = builder.to_dap_response(frames)
        assert "stackFrames" in response
        assert "totalFrames" in response
        assert response["totalFrames"] == len(frames)
        for sf in response["stackFrames"]:
            assert "id" in sf
            assert "name" in sf
            assert "source" in sf
            assert "line" in sf


# ============================================================
# VariableInspector Tests
# ============================================================


class TestVariableInspector:
    """Tests for the variable inspector."""

    def test_set_evaluation_context(self):
        inspector = VariableInspector()
        inspector.set_evaluation_context(15, "FizzBuzz", "FizzBuzz")
        scopes = inspector.get_scopes()
        assert any(s["name"] == "Evaluation" for s in scopes)

    def test_evaluation_variables_include_modulo(self):
        inspector = VariableInspector()
        inspector.set_evaluation_context(15, "FizzBuzz", "FizzBuzz")
        scopes = inspector.get_scopes()
        ref = [s for s in scopes if s["name"] == "Evaluation"][0]["variablesReference"]
        variables = inspector.get_variables(ref)
        var_names = {v["name"] for v in variables}
        assert "n" in var_names
        assert "n_mod_3" in var_names
        assert "n_mod_5" in var_names
        assert "is_fizzbuzz" in var_names

    def test_modulo_values_correct(self):
        inspector = VariableInspector()
        inspector.set_evaluation_context(15, "FizzBuzz", "FizzBuzz")
        scopes = inspector.get_scopes()
        ref = [s for s in scopes if s["name"] == "Evaluation"][0]["variablesReference"]
        variables = {v["name"]: v["value"] for v in inspector.get_variables(ref)}
        assert variables["n_mod_3"] == "0"
        assert variables["n_mod_5"] == "0"
        assert variables["is_fizzbuzz"] == "True"

    def test_set_cache_state(self):
        inspector = VariableInspector(include_cache=True)
        inspector.set_cache_state({"15": "FizzBuzz", "3": "Fizz"})
        assert inspector.scope_count >= 1

    def test_cache_disabled(self):
        inspector = VariableInspector(include_cache=False)
        inspector.set_cache_state({"15": "FizzBuzz"})
        # Should not create a Cache scope
        scopes = inspector.get_scopes()
        assert not any(s["name"] == "Cache" for s in scopes)

    def test_set_circuit_breaker_state(self):
        inspector = VariableInspector(include_circuit_breaker=True)
        inspector.set_circuit_breaker_state("OPEN", failure_count=5)
        scopes = inspector.get_scopes()
        assert any(s["name"] == "CircuitBreaker" for s in scopes)

    def test_set_quantum_state(self):
        inspector = VariableInspector(include_quantum=True)
        inspector.set_quantum_state([complex(0.5, 0.5), complex(0.5, -0.5)], num_qubits=1)
        scopes = inspector.get_scopes()
        assert any(s["name"] == "QuantumState" for s in scopes)

    def test_evaluate_modulo_expression(self):
        inspector = VariableInspector()
        inspector.set_evaluation_context(15, "FizzBuzz", "FizzBuzz")
        result = inspector.evaluate("n % 3")
        assert result == "0"

    def test_evaluate_arithmetic_expression(self):
        inspector = VariableInspector()
        inspector.set_evaluation_context(7, "7", "Plain")
        result = inspector.evaluate("n * 2 + 1")
        assert result == "15"

    def test_evaluate_boolean_expression(self):
        inspector = VariableInspector()
        inspector.set_evaluation_context(15, "FizzBuzz", "FizzBuzz")
        result = inspector.evaluate("is_fizzbuzz")
        assert result == "True"

    def test_evaluate_invalid_expression_raises(self):
        inspector = VariableInspector()
        inspector.set_evaluation_context(15, "FizzBuzz", "FizzBuzz")
        with pytest.raises(DAPEvaluationError, match="evaluate expression"):
            inspector.evaluate("undefined_var + 1")

    def test_total_variables(self):
        inspector = VariableInspector()
        inspector.set_evaluation_context(3, "Fizz", "Fizz")
        assert inspector.total_variables > 0

    def test_string_truncation(self):
        inspector = VariableInspector(max_string_length=10)
        inspector.set_evaluation_context(1, "A" * 100, "Plain")
        scopes = inspector.get_scopes()
        ref = [s for s in scopes if s["name"] == "Evaluation"][0]["variablesReference"]
        variables = {v["name"]: v["value"] for v in inspector.get_variables(ref)}
        assert len(variables["result"]) <= 10


# ============================================================
# DAPEventEmitter Tests
# ============================================================


class TestDAPEventEmitter:
    """Tests for DAP event emission."""

    def test_emit_stopped(self):
        session = DAPSession()
        emitter = DAPEventEmitter(session)
        msg = emitter.emit_stopped("breakpoint", "Hit breakpoint #1")
        assert msg.msg_type == "event"
        assert msg.command == "stopped"
        assert msg.body["reason"] == "breakpoint"

    def test_emit_continued(self):
        session = DAPSession()
        emitter = DAPEventEmitter(session)
        msg = emitter.emit_continued()
        assert msg.command == "continued"

    def test_emit_terminated(self):
        session = DAPSession()
        emitter = DAPEventEmitter(session)
        msg = emitter.emit_terminated()
        assert msg.command == "terminated"

    def test_emit_output(self):
        session = DAPSession()
        emitter = DAPEventEmitter(session)
        msg = emitter.emit_output("console", "Hello FizzBuzz")
        assert msg.command == "output"
        assert msg.body["output"] == "Hello FizzBuzz"

    def test_event_count(self):
        session = DAPSession()
        emitter = DAPEventEmitter(session)
        emitter.emit_stopped("entry")
        emitter.emit_continued()
        emitter.emit_terminated()
        assert emitter.event_count == 3

    def test_events_list(self):
        session = DAPSession()
        emitter = DAPEventEmitter(session)
        emitter.emit_stopped("step")
        events = emitter.events
        assert len(events) == 1
        assert events[0].command == "stopped"


# ============================================================
# FizzDAPServer Tests
# ============================================================


class TestFizzDAPServer:
    """Tests for the FizzDAP server command dispatch."""

    def test_initialize(self):
        server = FizzDAPServer()
        response = server.initialize()
        assert response.success is True
        assert response.command == "initialize"
        assert server.session.state == SessionState.INITIALIZED

    def test_dispatch_unknown_command(self):
        server = FizzDAPServer()
        server.initialize()
        req = DAPMessage(seq=99, msg_type="request", command="flyToMoon")
        resp = server.dispatch(req)
        assert resp.success is False
        assert "Unknown command" in resp.body.get("error", {}).get("format", "")

    def test_threads_response(self):
        server = FizzDAPServer()
        server.initialize()
        req = DAPMessage(seq=2, msg_type="request", command="threads")
        resp = server.dispatch(req)
        assert resp.success is True
        threads = resp.body["threads"]
        assert len(threads) == 1
        assert threads[0]["id"] == 1

    def test_set_breakpoints(self):
        server = FizzDAPServer()
        server.initialize()
        req = DAPMessage(seq=3, msg_type="request", command="setBreakpoints",
                         body={"breakpoints": [{"line": 15}, {"line": 3}]})
        resp = server.dispatch(req)
        assert resp.success is True
        assert len(resp.body["breakpoints"]) == 2

    def test_set_function_breakpoints(self):
        server = FizzDAPServer()
        server.initialize()
        req = DAPMessage(seq=4, msg_type="request", command="setFunctionBreakpoints",
                         body={"breakpoints": [{"name": "FizzBuzz"}]})
        resp = server.dispatch(req)
        assert resp.success is True
        assert resp.body["breakpoints"][0]["verified"] is True

    def test_stack_trace_response(self):
        server = FizzDAPServer()
        server.initialize()
        server.set_middleware_names(["CacheMiddleware", "SLAMiddleware"])
        server.session.current_number = 15
        req = DAPMessage(seq=5, msg_type="request", command="stackTrace",
                         body={"threadId": 1})
        resp = server.dispatch(req)
        assert resp.success is True
        assert resp.body["totalFrames"] >= 1

    def test_evaluate_expression(self):
        server = FizzDAPServer()
        server.initialize()
        server.var_inspector.set_evaluation_context(15, "FizzBuzz", "FizzBuzz")
        req = DAPMessage(seq=6, msg_type="request", command="evaluate",
                         body={"expression": "n % 3"})
        resp = server.dispatch(req)
        assert resp.success is True
        assert resp.body["result"] == "0"

    def test_evaluate_invalid_expression(self):
        server = FizzDAPServer()
        server.initialize()
        server.var_inspector.set_evaluation_context(15, "FizzBuzz", "FizzBuzz")
        req = DAPMessage(seq=7, msg_type="request", command="evaluate",
                         body={"expression": "completely_undefined_thing"})
        resp = server.dispatch(req)
        assert resp.success is False

    def test_continue_command(self):
        server = FizzDAPServer()
        server.initialize()
        server.session.transition_to(SessionState.RUNNING)
        server.session.transition_to(SessionState.STOPPED)
        req = DAPMessage(seq=8, msg_type="request", command="continue",
                         body={"threadId": 1})
        resp = server.dispatch(req)
        assert resp.success is True
        assert server.session.state == SessionState.RUNNING

    def test_step_in_command(self):
        server = FizzDAPServer()
        server.initialize()
        server.session.transition_to(SessionState.RUNNING)
        server.session.transition_to(SessionState.STOPPED)
        req = DAPMessage(seq=9, msg_type="request", command="stepIn",
                         body={"threadId": 1})
        resp = server.dispatch(req)
        assert resp.success is True

    def test_terminate_command(self):
        server = FizzDAPServer()
        server.initialize()
        resp = server.terminate()
        assert resp.success is True
        assert server.session.state == SessionState.TERMINATED

    def test_process_evaluation_auto_stop(self):
        server = FizzDAPServer(auto_stop_on_entry=True)
        server.initialize()
        result = server.process_evaluation(1, "1", "Plain")
        assert result["stopped"] is True
        assert server.session.stop_reason == "entry"

    def test_process_evaluation_breakpoint_hit(self):
        server = FizzDAPServer(auto_stop_on_entry=False)
        server.initialize()
        server.set_number_breakpoint(15)
        result = server.process_evaluation(15, "FizzBuzz", "FizzBuzz")
        assert result["stopped"] is True
        assert result["breakpoint"] is not None
        assert result["breakpoint"].number == 15

    def test_process_evaluation_no_stop(self):
        server = FizzDAPServer(auto_stop_on_entry=False)
        server.initialize()
        result = server.process_evaluation(7, "7", "Plain")
        assert result["stopped"] is False

    def test_process_evaluation_stepping(self):
        server = FizzDAPServer(auto_stop_on_entry=False)
        server.initialize()
        server.session.transition_to(SessionState.RUNNING)
        server.session.transition_to(SessionState.STOPPED)
        server.step_in()  # This sets _is_stepping = True and resumes
        result = server.process_evaluation(3, "Fizz", "Fizz")
        assert result["stopped"] is True
        assert server.session.stop_reason == "step"

    def test_dispatch_raw(self):
        server = FizzDAPServer()
        req = DAPMessage(seq=1, msg_type="request", command="initialize",
                         body={"clientID": "test"})
        raw_response = server.dispatch_raw(req.encode())
        assert "Content-Length:" in raw_response
        body = raw_response.split("\r\n\r\n", 1)[1]
        parsed = json.loads(body)
        assert parsed["success"] is True

    def test_set_classification_breakpoint_convenience(self):
        server = FizzDAPServer()
        bp = server.set_classification_breakpoint("Fizz")
        assert bp.classification == "Fizz"

    def test_message_log_tracks_messages(self):
        server = FizzDAPServer()
        server.initialize()
        # initialize sends 1 request + receives 1 response dispatched internally
        assert len(server.message_log) >= 2

    def test_scopes_response(self):
        server = FizzDAPServer()
        server.initialize()
        server.var_inspector.set_evaluation_context(3, "Fizz", "Fizz")
        req = DAPMessage(seq=10, msg_type="request", command="scopes",
                         body={"frameId": 1})
        resp = server.dispatch(req)
        assert resp.success is True
        assert len(resp.body["scopes"]) > 0

    def test_variables_response(self):
        server = FizzDAPServer()
        server.initialize()
        server.var_inspector.set_evaluation_context(3, "Fizz", "Fizz")
        scopes = server.var_inspector.get_scopes()
        ref = scopes[0]["variablesReference"]
        req = DAPMessage(seq=11, msg_type="request", command="variables",
                         body={"variablesReference": ref})
        resp = server.dispatch(req)
        assert resp.success is True
        assert len(resp.body["variables"]) > 0

    def test_pause_command(self):
        server = FizzDAPServer()
        server.initialize()
        server.session.transition_to(SessionState.RUNNING)
        req = DAPMessage(seq=12, msg_type="request", command="pause",
                         body={"threadId": 1})
        resp = server.dispatch(req)
        assert resp.success is True
        assert server.session.state == SessionState.STOPPED

    def test_disconnect_command(self):
        server = FizzDAPServer()
        server.initialize()
        req = DAPMessage(seq=13, msg_type="request", command="disconnect")
        resp = server.dispatch(req)
        assert resp.success is True
        assert server.session.state == SessionState.TERMINATED


# ============================================================
# FizzDAPDashboard Tests
# ============================================================


class TestFizzDAPDashboard:
    """Tests for the FizzDAP ASCII dashboard."""

    def test_render_basic(self):
        server = FizzDAPServer()
        server.initialize()
        output = FizzDAPDashboard.render(server)
        assert "FizzDAP" in output
        assert "SESSION STATE" in output

    def test_render_with_breakpoints(self):
        server = FizzDAPServer()
        server.initialize()
        server.set_number_breakpoint(15)
        server.set_classification_breakpoint("Fizz")
        output = FizzDAPDashboard.render(server, show_breakpoints=True)
        assert "BREAKPOINTS" in output
        assert "Number" in output

    def test_render_with_stack_trace(self):
        server = FizzDAPServer()
        server.initialize()
        server.set_middleware_names(["CacheMiddleware"])
        output = FizzDAPDashboard.render(server, show_stack_trace=True)
        assert "STACK TRACE" in output

    def test_render_with_variables(self):
        server = FizzDAPServer()
        server.initialize()
        server.var_inspector.set_evaluation_context(15, "FizzBuzz", "FizzBuzz")
        output = FizzDAPDashboard.render(server, show_variables=True)
        assert "VARIABLE INSPECTOR" in output

    def test_render_complexity_index(self):
        server = FizzDAPServer()
        server.initialize()
        output = FizzDAPDashboard.render(server, show_complexity_index=True)
        assert "DEBUG COMPLEXITY INDEX" in output
        assert "OVER-ENGINEERED" in output

    def test_render_no_breakpoints_message(self):
        server = FizzDAPServer()
        server.initialize()
        output = FizzDAPDashboard.render(server, show_breakpoints=True)
        assert "No breakpoints set" in output

    def test_render_custom_width(self):
        server = FizzDAPServer()
        server.initialize()
        output = FizzDAPDashboard.render(server, width=80)
        # Check that lines are approximately the right width
        for line in output.split("\n"):
            if line.startswith("|") or line.startswith("+"):
                assert len(line) == 80


# ============================================================
# Exception Tests
# ============================================================


class TestDAPExceptions:
    """Tests for DAP exception hierarchy."""

    def test_dap_error_base(self):
        err = DAPError("test error")
        assert "EFP-DAP0" in str(err)

    def test_dap_session_error(self):
        err = DAPSessionError("RUNNING", "terminate")
        assert "RUNNING" in str(err)
        assert "terminate" in str(err)
        assert err.error_code == "EFP-DAP1"

    def test_dap_breakpoint_error(self):
        err = DAPBreakpointError(42, "invalid condition")
        assert err.breakpoint_id == 42
        assert err.error_code == "EFP-DAP2"

    def test_dap_evaluation_error(self):
        err = DAPEvaluationError("n / 0", "ZeroDivisionError")
        assert err.expression == "n / 0"
        assert err.error_code == "EFP-DAP3"

    def test_dap_protocol_error(self):
        err = DAPProtocolError("header", "missing Content-Length")
        assert err.message_type == "header"
        assert err.error_code == "EFP-DAP4"

    def test_all_dap_errors_inherit_from_fizzbuzz_error(self):
        """Verify the exception hierarchy respects the domain model."""
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(DAPError, FizzBuzzError)
        assert issubclass(DAPSessionError, DAPError)
        assert issubclass(DAPBreakpointError, DAPError)
        assert issubclass(DAPEvaluationError, DAPError)
        assert issubclass(DAPProtocolError, DAPError)

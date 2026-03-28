"""
Enterprise FizzBuzz Platform - FizzPGWire PostgreSQL Wire Protocol Tests

Comprehensive test suite for the FizzPGWire subsystem, which implements
the PostgreSQL frontend/backend wire protocol for serving FizzBuzz
evaluation results over standard database connections.

Production database infrastructure demands rigorous validation of session
lifecycle management, authentication handshakes, query execution pipelines,
message encoding, and middleware integration. A PostgreSQL-compatible
interface to the FizzBuzz engine ensures seamless adoption by any tool
in the vast PostgreSQL ecosystem — psql, pgAdmin, JDBC drivers, and
thousands of BI platforms can connect out of the box.

Tests cover:
- Module-level constants (version, middleware priority)
- MessageType enum completeness
- PGMessage and PGSession dataclass construction
- QueryResult dataclass invariants
- PGWireServer session lifecycle (create, get, list, close)
- PGWireServer authentication flow
- PGWireServer query execution with BETWEEN ranges and FizzBuzz correctness
- PGWireServer statistics tracking
- PGWireServer message encoding
- FizzPGWireDashboard rendering
- FizzPGWireMiddleware IMiddleware contract
- create_fizzpgwire_subsystem factory wiring
- Exception hierarchy
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzpgwire import (
    FIZZPGWIRE_VERSION,
    MIDDLEWARE_PRIORITY,
    MessageType,
    PGMessage,
    PGSession,
    QueryResult,
    PGWireServer,
    FizzPGWireDashboard,
    FizzPGWireMiddleware,
    create_fizzpgwire_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzpgwire import (
    FizzPGWireError,
    FizzPGWireNotFoundError,
    FizzPGWireAuthError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons between tests to prevent cross-test contamination."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def server():
    """Provide a fresh PGWireServer instance."""
    return PGWireServer()


@pytest.fixture
def authenticated_session(server):
    """Create and authenticate a session, returning (server, session)."""
    session = server.create_session(database="fizzbuzz")
    authed = server.authenticate(session.session_id)
    return server, authed


# ============================================================
# Module Constants and MessageType Enum
# ============================================================


class TestModuleConstantsAndEnum:
    """Validate module-level exports and protocol message types."""

    def test_version_string(self):
        """The version must follow semver and be 1.0.0 for the initial release."""
        assert FIZZPGWIRE_VERSION == "1.0.0"

    def test_middleware_priority_is_221(self):
        """Priority 221 positions FizzPGWire after the SQL engine in the pipeline."""
        assert MIDDLEWARE_PRIORITY == 221

    def test_message_type_has_all_14_members(self):
        """The protocol subset defines exactly 14 message types."""
        expected = {
            "STARTUP", "AUTH", "QUERY", "PARSE", "BIND", "EXECUTE",
            "DESCRIBE", "SYNC", "TERMINATE", "ROW_DESCRIPTION",
            "DATA_ROW", "COMMAND_COMPLETE", "READY_FOR_QUERY",
            "ERROR_RESPONSE",
        }
        actual = {m.name for m in MessageType}
        assert actual == expected

    def test_message_type_count(self):
        assert len(MessageType) == 14


# ============================================================
# PGMessage / PGSession / QueryResult Dataclasses
# ============================================================


class TestDataclasses:
    """Wire protocol data structures must carry typed payloads faithfully."""

    def test_pg_message_construction(self):
        msg = PGMessage(msg_type=MessageType.QUERY, payload={"query": "SELECT 1"})
        assert msg.msg_type == MessageType.QUERY
        assert msg.payload == {"query": "SELECT 1"}

    def test_pg_session_fields(self):
        session = PGSession(
            session_id="abc-123", authenticated=False,
            database="fizzbuzz", parameters={"client_encoding": "UTF8"},
        )
        assert session.session_id == "abc-123"
        assert session.authenticated is False
        assert session.database == "fizzbuzz"
        assert session.parameters["client_encoding"] == "UTF8"

    def test_query_result_fields(self):
        qr = QueryResult(
            columns=["number", "result"],
            rows=[["1", "1"], ["2", "2"]],
            command_tag="SELECT",
            row_count=2,
        )
        assert qr.columns == ["number", "result"]
        assert len(qr.rows) == qr.row_count
        assert qr.command_tag == "SELECT"


# ============================================================
# PGWireServer — Session Lifecycle
# ============================================================


class TestPGWireServerSessionLifecycle:
    """Session create/get/list/close form the backbone of connection management."""

    def test_create_session_returns_unauthenticated_pg_session(self, server):
        session = server.create_session()
        assert isinstance(session, PGSession)
        assert session.authenticated is False
        assert session.database == "fizzbuzz"

    def test_create_session_custom_database(self, server):
        session = server.create_session(database="analytics")
        assert session.database == "analytics"

    def test_get_session_returns_created_session(self, server):
        session = server.create_session()
        retrieved = server.get_session(session.session_id)
        assert retrieved.session_id == session.session_id

    def test_get_session_nonexistent_raises(self, server):
        with pytest.raises(FizzPGWireNotFoundError):
            server.get_session("nonexistent-session-id")

    def test_list_sessions_tracks_creates(self, server):
        assert server.list_sessions() == []
        server.create_session()
        server.create_session()
        assert len(server.list_sessions()) == 2

    def test_close_session_removes_it(self, server):
        session = server.create_session()
        server.close_session(session.session_id)
        with pytest.raises(FizzPGWireNotFoundError):
            server.get_session(session.session_id)

    def test_close_nonexistent_session_raises(self, server):
        with pytest.raises(FizzPGWireNotFoundError):
            server.close_session("ghost-session")


# ============================================================
# PGWireServer — Authentication
# ============================================================


class TestPGWireServerAuthentication:
    """The authentication handshake gates all query execution."""

    def test_authenticate_sets_flag(self, server):
        session = server.create_session()
        authed = server.authenticate(session.session_id)
        assert authed.authenticated is True

    def test_authenticate_nonexistent_session_raises(self, server):
        with pytest.raises((FizzPGWireNotFoundError, FizzPGWireAuthError)):
            server.authenticate("does-not-exist")


# ============================================================
# PGWireServer — Query Execution
# ============================================================


class TestPGWireServerQueryExecution:
    """Query execution must return correct FizzBuzz results via SQL syntax."""

    def test_between_query_returns_correct_row_count(self, authenticated_session):
        srv, session = authenticated_session
        result = srv.execute_query(
            session.session_id,
            "SELECT * FROM fizzbuzz WHERE number BETWEEN 1 AND 5",
        )
        assert isinstance(result, QueryResult)
        assert result.row_count == 5
        assert len(result.columns) >= 1

    def test_fizzbuzz_correctness_at_15(self, authenticated_session):
        """Number 15 is divisible by both 3 and 5 and must produce FizzBuzz."""
        srv, session = authenticated_session
        result = srv.execute_query(
            session.session_id,
            "SELECT * FROM fizzbuzz WHERE number BETWEEN 15 AND 15",
        )
        assert result.row_count == 1
        row_values = " ".join(str(v).lower() for v in result.rows[0])
        assert "fizzbuzz" in row_values

    def test_fizz_correctness_at_3(self, authenticated_session):
        """Number 3 is divisible by 3 only and must produce Fizz."""
        srv, session = authenticated_session
        result = srv.execute_query(
            session.session_id,
            "SELECT * FROM fizzbuzz WHERE number BETWEEN 3 AND 3",
        )
        row_values = " ".join(str(v).lower() for v in result.rows[0])
        assert "fizz" in row_values

    def test_buzz_correctness_at_5(self, authenticated_session):
        """Number 5 is divisible by 5 only and must produce Buzz."""
        srv, session = authenticated_session
        result = srv.execute_query(
            session.session_id,
            "SELECT * FROM fizzbuzz WHERE number BETWEEN 5 AND 5",
        )
        row_values = " ".join(str(v).lower() for v in result.rows[0])
        assert "buzz" in row_values

    def test_command_tag_contains_select(self, authenticated_session):
        srv, session = authenticated_session
        result = srv.execute_query(
            session.session_id,
            "SELECT * FROM fizzbuzz WHERE number BETWEEN 1 AND 3",
        )
        assert "SELECT" in result.command_tag.upper()


# ============================================================
# PGWireServer — Statistics and Message Encoding
# ============================================================


class TestPGWireServerStatsAndEncoding:
    """Server statistics and message encoding for operational visibility."""

    def test_stats_returns_dict_with_required_keys(self, server):
        stats = server.get_stats()
        assert isinstance(stats, dict)
        assert "total_queries" in stats
        assert "active_sessions" in stats

    def test_stats_increments_after_query(self, authenticated_session):
        srv, session = authenticated_session
        before = srv.get_stats()["total_queries"]
        srv.execute_query(
            session.session_id,
            "SELECT * FROM fizzbuzz WHERE number BETWEEN 1 AND 1",
        )
        assert srv.get_stats()["total_queries"] == before + 1

    def test_active_sessions_tracks_count(self, server):
        server.create_session()
        server.create_session()
        assert server.get_stats()["active_sessions"] == 2

    def test_encode_message_returns_pg_message(self, server):
        msg = server.encode_message(MessageType.QUERY, {"query": "SELECT 1"})
        assert isinstance(msg, PGMessage)
        assert msg.msg_type == MessageType.QUERY

    def test_encode_message_preserves_payload(self, server):
        payload = {"columns": ["a", "b"]}
        msg = server.encode_message(MessageType.ROW_DESCRIPTION, payload)
        assert msg.payload == payload


# ============================================================
# Dashboard
# ============================================================


class TestFizzPGWireDashboard:
    """The dashboard renders an ASCII summary of PGWire server state."""

    def test_render_returns_nonempty_string(self):
        dashboard = FizzPGWireDashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0


# ============================================================
# Middleware
# ============================================================


class TestFizzPGWireMiddleware:
    """The middleware integrates PGWire protocol handling into the pipeline."""

    def test_name_and_priority(self):
        mw = FizzPGWireMiddleware()
        assert mw.get_name() == "fizzpgwire"
        assert mw.get_priority() == 221

    def test_process_delegates_to_next_handler(self):
        """The middleware must invoke the next handler and return a ProcessingContext."""
        mw = FizzPGWireMiddleware()
        ctx = ProcessingContext(number=15, session_id="test-session")
        result = mw.process(ctx, lambda c: c)
        assert isinstance(result, ProcessingContext)
        assert result.number == 15


# ============================================================
# Factory
# ============================================================


class TestCreateFizzPGWireSubsystem:
    """The factory must return a correctly-wired triple of components."""

    def test_factory_returns_server_dashboard_middleware(self):
        server, dashboard, middleware = create_fizzpgwire_subsystem()
        assert isinstance(server, PGWireServer)
        assert isinstance(dashboard, FizzPGWireDashboard)
        assert isinstance(middleware, FizzPGWireMiddleware)


# ============================================================
# Exception Hierarchy
# ============================================================


class TestFizzPGWireExceptions:
    """The exception hierarchy must follow platform error code conventions."""

    def test_base_error_is_catchable(self):
        with pytest.raises(FizzPGWireError):
            raise FizzPGWireError("test failure")

    def test_not_found_inherits_base_with_correct_code(self):
        err = FizzPGWireNotFoundError("session-xyz")
        assert isinstance(err, FizzPGWireError)
        assert err.error_code == "EFP-PGW01"

    def test_auth_error_inherits_base_with_correct_code(self):
        err = FizzPGWireAuthError("bad password")
        assert isinstance(err, FizzPGWireError)
        assert err.error_code == "EFP-PGW02"

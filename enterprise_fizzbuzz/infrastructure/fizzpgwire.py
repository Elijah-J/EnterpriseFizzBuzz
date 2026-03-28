"""Enterprise FizzBuzz Platform - FizzPGWire: PostgreSQL Wire Protocol Server"""
from __future__ import annotations
import logging, re, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzpgwire import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzpgwire")
EVENT_PGWIRE = EventType.register("FIZZPGWIRE_QUERY")
FIZZPGWIRE_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 221


class MessageType(Enum):
    STARTUP = "startup"
    AUTH = "auth"
    QUERY = "query"
    PARSE = "parse"
    BIND = "bind"
    EXECUTE = "execute"
    DESCRIBE = "describe"
    SYNC = "sync"
    TERMINATE = "terminate"
    ROW_DESCRIPTION = "row_description"
    DATA_ROW = "data_row"
    COMMAND_COMPLETE = "command_complete"
    READY_FOR_QUERY = "ready_for_query"
    ERROR_RESPONSE = "error_response"


@dataclass
class PGMessage:
    """A PostgreSQL wire protocol message."""
    msg_type: MessageType = MessageType.QUERY
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PGSession:
    """A PostgreSQL client session."""
    session_id: str = ""
    authenticated: bool = False
    database: str = "fizzbuzz"
    parameters: Dict[str, str] = field(default_factory=dict)


@dataclass
class QueryResult:
    """The result of executing a SQL query."""
    columns: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    command_tag: str = ""
    row_count: int = 0


@dataclass
class FizzPGWireConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


BETWEEN_RE = re.compile(
    r"SELECT\s+\*\s+FROM\s+fizzbuzz\s+WHERE\s+number\s+BETWEEN\s+(\d+)\s+AND\s+(\d+)",
    re.IGNORECASE,
)


def _fizzbuzz(n: int) -> str:
    """Compute the FizzBuzz classification for a single number."""
    if n % 15 == 0:
        return "FizzBuzz"
    elif n % 3 == 0:
        return "Fizz"
    elif n % 5 == 0:
        return "Buzz"
    else:
        return str(n)


class PGWireServer:
    """Implements the PostgreSQL frontend/backend wire protocol, serving
    FizzBuzz results through standard SQL queries."""

    def __init__(self) -> None:
        self._sessions: OrderedDict[str, PGSession] = OrderedDict()
        self._total_queries = 0

    def create_session(self, database: str = "fizzbuzz") -> PGSession:
        """Create a new client session."""
        session_id = f"pg-{uuid.uuid4().hex[:8]}"
        session = PGSession(
            session_id=session_id,
            database=database,
            parameters={"server_version": "15.0", "server_encoding": "UTF8"},
        )
        self._sessions[session_id] = session
        return session

    def authenticate(self, session_id: str, password: str = "") -> PGSession:
        """Authenticate a session. The FizzBuzz database accepts all passwords."""
        session = self.get_session(session_id)
        session.authenticated = True
        return session

    def execute_query(self, session_id: str, query: str) -> QueryResult:
        """Execute a SQL query against the FizzBuzz database."""
        session = self.get_session(session_id)
        if not session.authenticated:
            raise FizzPGWireAuthError("Session not authenticated")
        self._total_queries += 1

        # Parse BETWEEN queries
        match = BETWEEN_RE.match(query.strip())
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            rows = [[str(n), _fizzbuzz(n)] for n in range(start, end + 1)]
            return QueryResult(
                columns=["number", "result"],
                rows=rows,
                command_tag=f"SELECT {len(rows)}",
                row_count=len(rows),
            )

        # SELECT version()
        if re.match(r"SELECT\s+version\(\)", query.strip(), re.IGNORECASE):
            return QueryResult(
                columns=["version"],
                rows=[["FizzPGWire 1.0.0 (Enterprise FizzBuzz Platform)"]],
                command_tag="SELECT 1",
                row_count=1,
            )

        # Default: empty result
        return QueryResult(
            columns=[],
            rows=[],
            command_tag="SELECT 0",
            row_count=0,
        )

    def close_session(self, session_id: str) -> None:
        """Close and remove a session."""
        if session_id not in self._sessions:
            raise FizzPGWireNotFoundError(session_id)
        del self._sessions[session_id]

    def get_session(self, session_id: str) -> PGSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise FizzPGWireNotFoundError(session_id)
        return session

    def list_sessions(self) -> List[PGSession]:
        return list(self._sessions.values())

    def encode_message(self, msg_type: MessageType, payload: dict) -> PGMessage:
        """Encode a message in PG wire format."""
        return PGMessage(msg_type=msg_type, payload=payload)

    def get_stats(self) -> dict:
        return {
            "total_queries": self._total_queries,
            "active_sessions": len(self._sessions),
        }


class FizzPGWireDashboard:
    def __init__(self, server: Optional[PGWireServer] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._server = server
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzPGWire Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZPGWIRE_VERSION}"]
        if self._server:
            stats = self._server.get_stats()
            lines.append(f"  Active Sessions: {stats['active_sessions']}")
            lines.append(f"  Total Queries: {stats['total_queries']}")
        return "\n".join(lines)


class FizzPGWireMiddleware(IMiddleware):
    def __init__(self, server: Optional[PGWireServer] = None,
                 dashboard: Optional[FizzPGWireDashboard] = None) -> None:
        self._server = server
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzpgwire"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzpgwire_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[PGWireServer, FizzPGWireDashboard, FizzPGWireMiddleware]:
    """Factory function that creates and wires the FizzPGWire subsystem."""
    server = PGWireServer()
    dashboard = FizzPGWireDashboard(server, dashboard_width)
    middleware = FizzPGWireMiddleware(server, dashboard)
    logger.info("FizzPGWire initialized")
    return server, dashboard, middleware

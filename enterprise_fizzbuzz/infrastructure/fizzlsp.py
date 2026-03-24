"""
Enterprise FizzBuzz Platform - FizzLSP: Language Server Protocol for FizzLang

A complete Language Server Protocol implementation for the FizzLang domain-specific
language, providing real-time IDE intelligence to developers writing FizzLang
programs.  The server communicates via JSON-RPC 2.0 over stdio or TCP using the
same Content-Length framing that FizzDAP established for the Debug Adapter
Protocol.  It supports the full document synchronization lifecycle with
incremental text synchronization, context-aware completions, inline diagnostics
from four analysis passes (lexer, parser, type checker, dependent type system),
go-to-definition for variables and rules and stdlib functions, hover
documentation with type information and FizzBuzz classification of literals,
find-all-references with AST walking and comment scanning, scope-aware rename
with conflict detection, workspace symbol search, full semantic token
classification for syntax highlighting, code actions (quick fixes and
refactoring), and document formatting according to canonical FizzLang style.

The server is SIMULATED -- no actual socket is opened, no actual editor connects.
All protocol logic and message dispatch operates in-memory for testing and CLI
integration.  This follows the established pattern set by FizzDAP, the TCP/IP
stack, the DNS server, the HTTP/2 server, and every other network-facing
subsystem in the platform.  The language server exists to be correct, not to be
connected.

The platform has a lexer that knows every token type.  It has a parser that knows
the grammar.  It has a type checker that knows about scoping and arities.  It has
a dependent type system that knows about proof obligations.  All of this knowledge
is locked inside batch-mode tools.  LSP is the key that converts batch-mode
analysis into interactive, as-you-type intelligence.  The knowledge is there.
The delivery mechanism was not.

Architecture reference: Microsoft LSP specification 3.17, rust-analyzer, pylsp,
tsserver, clangd, gopls
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import re
import time
import uuid
from collections import defaultdict, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from io import StringIO
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions import (
    FizzLSPError,
    FizzLSPTransportError,
    FizzLSPProtocolError,
    FizzLSPSessionError,
    FizzLSPDocumentError,
    FizzLSPDocumentSyncError,
    FizzLSPAnalysisError,
    FizzLSPCompletionError,
    FizzLSPDiagnosticError,
    FizzLSPDefinitionError,
    FizzLSPHoverError,
    FizzLSPReferencesError,
    FizzLSPRenameError,
    FizzLSPRenameConflictError,
    FizzLSPSemanticTokenError,
    FizzLSPCodeActionError,
    FizzLSPFormattingError,
    FizzLSPSymbolError,
    FizzLSPDispatchError,
    FizzLSPMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzlsp")

# ============================================================
# Constants
# ============================================================

FIZZLSP_VERSION = "1.0.0"
"""FizzLSP language server version."""

FIZZLSP_SERVER_NAME = "FizzLSP"
"""Server name reported in InitializeResult."""

DEFAULT_TRANSPORT = "stdio"
"""Default transport type."""

DEFAULT_TCP_PORT = 5007
"""Default TCP port for the TCP transport."""

DEFAULT_DIAGNOSTIC_DEBOUNCE_MS = 150
"""Default debounce interval for diagnostic publication in milliseconds."""

DEFAULT_MAX_COMPLETION_ITEMS = 50
"""Maximum number of completion items returned per request."""

DEFAULT_DASHBOARD_WIDTH = 60
"""Default width for the FizzLSP ASCII dashboard."""

MAX_PARSE_RECOVERY_ATTEMPTS = 3
"""Maximum error recovery attempts per parse."""

LEVENSHTEIN_THRESHOLD = 2
"""Maximum Levenshtein distance for typo suggestions."""

MIDDLEWARE_PRIORITY = 92
"""Middleware pipeline priority for FizzLSP."""

# JSON-RPC 2.0 error codes
JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603

# LSP-specific error codes
LSP_SERVER_NOT_INITIALIZED = -32002
LSP_REQUEST_CANCELLED = -32800
LSP_CONTENT_MODIFIED = -32801

# FizzLang reserved keywords
_FIZZLANG_KEYWORDS: Set[str] = {
    "rule", "when", "emit", "evaluate", "to", "let", "priority",
    "and", "or", "not", "true", "false",
}

# FizzLang stdlib function names
_STDLIB_FUNCTIONS: Set[str] = {"is_prime", "fizzbuzz", "range"}


# ============================================================
# Enums
# ============================================================


class LSPServerState(Enum):
    """Server lifecycle state machine.

    UNINITIALIZED -> INITIALIZING -> RUNNING -> SHUTTING_DOWN -> TERMINATED.
    Invalid transitions raise FizzLSPProtocolError.  This mirrors FizzDAP's
    SessionState pattern but with LSP-specific states.
    """
    UNINITIALIZED = auto()
    INITIALIZING = auto()
    RUNNING = auto()
    SHUTTING_DOWN = auto()
    TERMINATED = auto()


# Valid state transitions.
VALID_TRANSITIONS: Dict[LSPServerState, Set[LSPServerState]] = {
    LSPServerState.UNINITIALIZED: {LSPServerState.INITIALIZING},
    LSPServerState.INITIALIZING: {LSPServerState.RUNNING, LSPServerState.TERMINATED},
    LSPServerState.RUNNING: {LSPServerState.SHUTTING_DOWN, LSPServerState.TERMINATED},
    LSPServerState.SHUTTING_DOWN: {LSPServerState.TERMINATED},
    LSPServerState.TERMINATED: set(),
}


def _validate_transition(current: LSPServerState, target: LSPServerState) -> None:
    """Validate a server state transition.  Raises FizzLSPProtocolError for invalid transitions."""
    if target not in VALID_TRANSITIONS.get(current, set()):
        # Allow any state -> TERMINATED for abnormal exit
        if target == LSPServerState.TERMINATED:
            return
        raise FizzLSPProtocolError(current.name, f"transition to {target.name}")


class LSPMessageType(Enum):
    """JSON-RPC 2.0 message classification."""
    REQUEST = auto()       # Has id and method
    RESPONSE = auto()      # Has id and result/error
    NOTIFICATION = auto()  # Has method but no id


class TextDocumentSyncKind(Enum):
    """How the client sends document changes to the server."""
    NONE = 0
    FULL = 1
    INCREMENTAL = 2


class DiagnosticSeverity(Enum):
    """LSP diagnostic severity levels."""
    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4


class DiagnosticTag(Enum):
    """LSP diagnostic tags."""
    UNNECESSARY = 1
    DEPRECATED = 2


class CompletionItemKind(Enum):
    """LSP completion item kinds used by FizzLSP."""
    TEXT = 1
    METHOD = 2
    FUNCTION = 3
    FIELD = 4
    VARIABLE = 6
    KEYWORD = 14
    SNIPPET = 15
    OPERATOR = 24
    PROPERTY = 10


class InsertTextFormat(Enum):
    """Insert text format for completion items."""
    PLAIN_TEXT = 1
    SNIPPET = 2


class SymbolKind(Enum):
    """LSP symbol kinds used by FizzLSP."""
    FUNCTION = 12    # Rules
    VARIABLE = 13    # Let-bindings
    BOOLEAN = 17     # Rule conditions
    STRING = 15      # Emit expressions
    NUMBER = 16      # Priority values
    EVENT = 24       # Evaluate statements
    METHOD = 6       # Stdlib functions


class CodeActionKind(Enum):
    """LSP code action kinds supported by FizzLSP."""
    QUICKFIX = "quickfix"
    REFACTOR_EXTRACT = "refactor.extract"
    REFACTOR_REWRITE = "refactor.rewrite"
    SOURCE_FIXALL = "source.fixAll"


class SemanticTokenType(Enum):
    """Semantic token type legend indices."""
    KEYWORD = 0
    VARIABLE = 1
    FUNCTION = 2
    STRING = 3
    NUMBER = 4
    OPERATOR = 5
    COMMENT = 6
    TYPE = 7
    PARAMETER = 8
    PROPERTY = 9
    NAMESPACE = 10
    ENUM_MEMBER = 11


class SemanticTokenModifier(Enum):
    """Semantic token modifier legend bit positions."""
    DECLARATION = 0
    DEFINITION = 1
    READONLY = 2
    STATIC = 3
    DEPRECATED = 4
    MODIFICATION = 5
    DOCUMENTATION = 6
    DEFAULT_LIBRARY = 7


# ============================================================
# Data Classes
# ============================================================


@dataclass
class LSPPosition:
    """Zero-indexed line and character position in a text document."""
    line: int
    character: int


@dataclass
class LSPRange:
    """A range in a text document, defined by start and end positions."""
    start: LSPPosition
    end: LSPPosition


@dataclass
class LSPLocation:
    """A location in a document, identified by URI and range."""
    uri: str
    range: LSPRange


@dataclass
class LSPMessage:
    """JSON-RPC 2.0 message with Content-Length header framing.

    Follows the identical wire format as DAPMessage:
    Content-Length: N\\r\\n\\r\\n{json_body}

    Content-Length is computed from the UTF-8 encoded body, not from
    Python len(), because the LSP specification mandates byte-level
    content length.
    """
    jsonrpc: str = "2.0"
    id: Optional[Union[int, str]] = None
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None

    @property
    def message_type(self) -> LSPMessageType:
        """Classify this message as request, response, or notification."""
        if self.id is not None and self.method is not None:
            return LSPMessageType.REQUEST
        if self.id is not None and (self.result is not None or self.error is not None):
            return LSPMessageType.RESPONSE
        if self.method is not None and self.id is None:
            return LSPMessageType.NOTIFICATION
        if self.id is not None:
            return LSPMessageType.RESPONSE
        return LSPMessageType.NOTIFICATION

    @property
    def is_request(self) -> bool:
        return self.message_type == LSPMessageType.REQUEST

    @property
    def is_response(self) -> bool:
        return self.message_type == LSPMessageType.RESPONSE

    @property
    def is_notification(self) -> bool:
        return self.message_type == LSPMessageType.NOTIFICATION

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        d: Dict[str, Any] = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            d["id"] = self.id
        if self.method is not None:
            d["method"] = self.method
        if self.params is not None:
            d["params"] = self.params
        if self.result is not None:
            d["result"] = self.result
        if self.error is not None:
            d["error"] = self.error
        return d

    def encode(self) -> str:
        """Encode this message in LSP wire format with Content-Length framing.

        Returns the full wire representation:
        ``Content-Length: N\\r\\n\\r\\n{json_body}``
        """
        json_body = json.dumps(self.to_dict(), separators=(",", ":"))
        content_length = len(json_body.encode("utf-8"))
        return f"Content-Length: {content_length}\r\n\r\n{json_body}"

    @classmethod
    def decode(cls, raw: str) -> LSPMessage:
        """Decode a message from LSP wire format.

        Parses the Content-Length header, extracts the JSON body, and
        constructs an LSPMessage instance.
        """
        if not raw:
            raise FizzLSPTransportError("Empty message", raw_data=raw)

        # Find the header/body separator
        separator = "\r\n\r\n"
        sep_index = raw.find(separator)
        if sep_index == -1:
            raise FizzLSPTransportError(
                "Missing header/body separator (\\r\\n\\r\\n)", raw_data=raw
            )

        header_part = raw[:sep_index]
        body_part = raw[sep_index + len(separator):]

        # Parse Content-Length
        content_length = None
        for line in header_part.split("\r\n"):
            if line.lower().startswith("content-length:"):
                try:
                    content_length = int(line.split(":", 1)[1].strip())
                except ValueError:
                    raise FizzLSPTransportError(
                        f"Non-integer Content-Length: {line}", raw_data=raw
                    )
                break

        if content_length is None:
            raise FizzLSPTransportError(
                "Missing Content-Length header", raw_data=raw
            )

        # Validate body length
        body_bytes = body_part.encode("utf-8")
        if len(body_bytes) < content_length:
            raise FizzLSPTransportError(
                f"Truncated body: expected {content_length} bytes, got {len(body_bytes)}",
                raw_data=raw,
            )

        # Parse JSON body (use only the declared number of bytes)
        json_str = body_bytes[:content_length].decode("utf-8")
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise FizzLSPTransportError(
                f"Invalid JSON in message body: {e}", raw_data=raw
            )

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LSPMessage:
        """Construct an LSPMessage from a parsed JSON dictionary."""
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            method=data.get("method"),
            params=data.get("params"),
            result=data.get("result"),
            error=data.get("error"),
        )


@dataclass
class TextDocumentItem:
    """An open document with URI, language ID, version, and full text content.

    The version number increases monotonically with each edit and is used
    to detect out-of-order notifications.
    """
    uri: str
    language_id: str  # "fizzlang"
    version: int
    text: str


@dataclass
class LSPDiagnostic:
    """An LSP diagnostic: error, warning, information, or hint."""
    range: LSPRange
    severity: DiagnosticSeverity
    code: str                            # e.g., "EFP-FL11", "EFP-LSP1"
    source: str = "FizzLSP"
    message: str = ""
    related_information: List[Dict[str, Any]] = field(default_factory=list)
    tags: List[DiagnosticTag] = field(default_factory=list)


@dataclass
class SymbolInfo:
    """Information about a symbol in the FizzLang program."""
    name: str
    kind: str                            # "rule", "variable", "function", "keyword"
    definition_location: LSPLocation
    type_info: str                       # e.g., "int", "string", "bool", "(int) -> bool"
    documentation: str = ""
    references: List[LSPLocation] = field(default_factory=list)
    scope: str = "top-level"


@dataclass
class SymbolTable:
    """Maps symbol names to SymbolInfo records.

    Rebuilt on every document change because FizzLang's scoping rules are
    simple (all let-bindings are top-level) and the rebuild is sub-millisecond.
    """
    symbols: Dict[str, SymbolInfo] = field(default_factory=dict)

    def add_symbol(self, info: SymbolInfo) -> None:
        """Register a symbol in the table."""
        self.symbols[info.name] = info

    def get_symbol(self, name: str) -> Optional[SymbolInfo]:
        """Look up a symbol by name."""
        return self.symbols.get(name)

    def find_at_position(self, uri: str, position: LSPPosition) -> Optional[SymbolInfo]:
        """Find the symbol defined at the given position."""
        for info in self.symbols.values():
            loc = info.definition_location
            if loc.uri == uri:
                r = loc.range
                if (r.start.line == position.line and
                        r.start.character <= position.character <= r.end.character):
                    return info
        return None

    def find_references(self, name: str) -> List[LSPLocation]:
        """Return all reference locations for a symbol."""
        info = self.symbols.get(name)
        if info is None:
            return []
        return list(info.references)

    def find_similar_name(self, name: str) -> Optional[str]:
        """Find the most similar symbol name within Levenshtein threshold."""
        best = None
        best_dist = LEVENSHTEIN_THRESHOLD + 1
        for existing in self.symbols:
            d = _levenshtein(name, existing)
            if d < best_dist:
                best_dist = d
                best = existing
        return best if best_dist <= LEVENSHTEIN_THRESHOLD else None

    def all_rules(self) -> List[SymbolInfo]:
        return [s for s in self.symbols.values() if s.kind == "rule"]

    def all_variables(self) -> List[SymbolInfo]:
        return [s for s in self.symbols.values() if s.kind == "variable"]

    def all_functions(self) -> List[SymbolInfo]:
        return [s for s in self.symbols.values() if s.kind == "function"]

    def to_list(self) -> List[SymbolInfo]:
        return list(self.symbols.values())


@dataclass
class AnalysisResult:
    """The product of the analysis pipeline for a single document."""
    diagnostics: List[LSPDiagnostic] = field(default_factory=list)
    ast: Any = None                      # ProgramNode or None
    tokens: List[Any] = field(default_factory=list)
    symbol_table: SymbolTable = field(default_factory=SymbolTable)
    semantic_tokens: List[Tuple[int, int, int, int, int]] = field(default_factory=list)
    analysis_time_ms: float = 0.0


@dataclass
class CompletionItem:
    """A single completion suggestion."""
    label: str
    kind: CompletionItemKind
    detail: str = ""
    documentation: str = ""
    insert_text: str = ""
    insert_text_format: InsertTextFormat = InsertTextFormat.PLAIN_TEXT
    sort_text: str = ""
    filter_text: str = ""
    commit_characters: List[str] = field(default_factory=list)
    additional_text_edits: List[Dict[str, Any]] = field(default_factory=list)
    data: Optional[Dict[str, Any]] = None  # For resolve

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"label": self.label, "kind": self.kind.value}
        if self.detail:
            d["detail"] = self.detail
        if self.documentation:
            d["documentation"] = self.documentation
        if self.insert_text:
            d["insertText"] = self.insert_text
        if self.insert_text_format != InsertTextFormat.PLAIN_TEXT:
            d["insertTextFormat"] = self.insert_text_format.value
        if self.sort_text:
            d["sortText"] = self.sort_text
        if self.filter_text:
            d["filterText"] = self.filter_text
        if self.commit_characters:
            d["commitCharacters"] = self.commit_characters
        if self.data:
            d["data"] = self.data
        return d


@dataclass
class TextEdit:
    """A text edit applied to a document."""
    range: LSPRange
    new_text: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "range": {
                "start": {"line": self.range.start.line, "character": self.range.start.character},
                "end": {"line": self.range.end.line, "character": self.range.end.character},
            },
            "newText": self.new_text,
        }


@dataclass
class WorkspaceEdit:
    """A set of text edits across documents."""
    changes: Dict[str, List[TextEdit]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "changes": {
                uri: [e.to_dict() for e in edits]
                for uri, edits in self.changes.items()
            }
        }


@dataclass
class DocumentSymbol:
    """A symbol in the document outline."""
    name: str
    detail: str
    kind: SymbolKind
    range: LSPRange
    selection_range: LSPRange
    children: List[DocumentSymbol] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "detail": self.detail,
            "kind": self.kind.value,
            "range": {
                "start": {"line": self.range.start.line, "character": self.range.start.character},
                "end": {"line": self.range.end.line, "character": self.range.end.character},
            },
            "selectionRange": {
                "start": {"line": self.selection_range.start.line, "character": self.selection_range.start.character},
                "end": {"line": self.selection_range.end.line, "character": self.selection_range.end.character},
            },
        }
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


@dataclass
class SemanticTokenData:
    """Raw semantic token before delta encoding."""
    line: int
    start_char: int
    length: int
    token_type: SemanticTokenType
    modifiers: int = 0  # Bitset of SemanticTokenModifier values


@dataclass
class LSPServerCapabilities:
    """The full set of capabilities the FizzLSP server supports.

    Declared during the initialize handshake.  Each capability maps to
    a provider class that implements the corresponding LSP method.
    """
    text_document_sync: int = TextDocumentSyncKind.INCREMENTAL.value
    completion_provider: Dict[str, Any] = field(default_factory=lambda: {
        "triggerCharacters": [".", "%", "(", " "],
        "resolveProvider": True,
    })
    hover_provider: bool = True
    definition_provider: bool = True
    references_provider: bool = True
    rename_provider: Dict[str, Any] = field(default_factory=lambda: {"prepareProvider": True})
    document_symbol_provider: bool = True
    workspace_symbol_provider: bool = True
    semantic_tokens_provider: Dict[str, Any] = field(default_factory=lambda: {
        "full": True,
        "range": True,
        "legend": {
            "tokenTypes": [t.name.lower() for t in SemanticTokenType],
            "tokenModifiers": [m.name.lower() for m in SemanticTokenModifier],
        },
    })
    code_action_provider: Dict[str, Any] = field(default_factory=lambda: {
        "codeActionKinds": [k.value for k in CodeActionKind],
    })
    document_formatting_provider: bool = True
    diagnostic_provider: Dict[str, Any] = field(default_factory=lambda: {
        "interFileDiagnostics": False,
        "workspaceDiagnostics": False,
    })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "textDocumentSync": self.text_document_sync,
            "completionProvider": self.completion_provider,
            "hoverProvider": self.hover_provider,
            "definitionProvider": self.definition_provider,
            "referencesProvider": self.references_provider,
            "renameProvider": self.rename_provider,
            "documentSymbolProvider": self.document_symbol_provider,
            "workspaceSymbolProvider": self.workspace_symbol_provider,
            "semanticTokensProvider": self.semantic_tokens_provider,
            "codeActionProvider": self.code_action_provider,
            "documentFormattingProvider": self.document_formatting_provider,
            "diagnosticProvider": self.diagnostic_provider,
        }


@dataclass
class FizzLSPMetrics:
    """Tracks server performance metrics."""
    requests_processed: int = 0
    avg_response_time_ms: Dict[str, float] = field(default_factory=dict)
    diagnostics_published: int = 0
    completions_served: int = 0
    definitions_resolved: int = 0
    hovers_served: int = 0
    renames_performed: int = 0
    formatting_applied: int = 0
    start_time: float = field(default_factory=time.monotonic)


# ============================================================
# Utility Functions
# ============================================================


def _levenshtein(a: str, b: str) -> int:
    """Standard dynamic-programming Levenshtein edit distance.

    Used by the diagnostic publisher for typo suggestions and by
    the code action provider for similar-identifier fixes.
    """
    if len(a) < len(b):
        return _levenshtein(b, a)
    if len(b) == 0:
        return len(a)
    prev_row = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr_row = [i + 1]
        for j, cb in enumerate(b):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (0 if ca == cb else 1)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def _infer_type(node: Any) -> str:
    """Infer the type of an AST expression node.

    Integer literals -> 'int', string literals -> 'string', boolean
    literals -> 'bool', arithmetic expressions -> 'int', comparison
    expressions -> 'bool', function calls -> function return type.
    """
    from enterprise_fizzbuzz.infrastructure.fizzlang import (
        BinaryOpNode,
        FunctionCallNode,
        IdentifierNode,
        LiteralNode,
        NVarNode,
        UnaryOpNode,
    )

    if isinstance(node, LiteralNode):
        v = node.value
        if isinstance(v, bool):
            return "bool"
        if isinstance(v, int):
            return "int"
        if isinstance(v, str):
            return "string"
        return "unknown"
    if isinstance(node, NVarNode):
        return "int"
    if isinstance(node, IdentifierNode):
        return "unknown"  # Would need symbol table context
    if isinstance(node, BinaryOpNode):
        if node.op in ("==", "!=", "<", ">", "<=", ">=", "and", "or"):
            return "bool"
        return "int"
    if isinstance(node, UnaryOpNode):
        if node.op == "not":
            return "bool"
        return "int"
    if isinstance(node, FunctionCallNode):
        fn_types = {"is_prime": "bool", "fizzbuzz": "string", "range": "list"}
        return fn_types.get(node.name, "unknown")
    return "unknown"


# ============================================================
# JSON-RPC Transport Layer
# ============================================================


class LSPTransport:
    """Abstract base class for LSP transports."""

    def send(self, message: LSPMessage) -> None:
        raise NotImplementedError

    def receive(self) -> Optional[LSPMessage]:
        raise NotImplementedError


class StdioTransport(LSPTransport):
    """In-memory stdio transport using StringIO buffers.

    Reads from and writes to in-memory StringIO buffers, simulating
    the standard input/output streams that a real LSP server would use.
    """

    def __init__(
        self,
        input_buffer: Optional[StringIO] = None,
        output_buffer: Optional[StringIO] = None,
    ) -> None:
        self._input = input_buffer or StringIO()
        self._output = output_buffer or StringIO()

    def send(self, message: LSPMessage) -> None:
        self._output.write(message.encode())

    def receive(self) -> Optional[LSPMessage]:
        """Read a message from the input buffer.

        Returns None if the buffer is exhausted.
        """
        content = self._input.read()
        if not content or not content.strip():
            return None
        try:
            return LSPMessage.decode(content)
        except FizzLSPTransportError:
            return None

    def get_output(self) -> str:
        self._output.seek(0)
        return self._output.read()


class TCPTransport(LSPTransport):
    """Simulated TCP transport using in-memory byte buffer pairs.

    No actual socket is opened.  Client-to-server and server-to-client
    communication occurs through in-memory bytearray buffers with
    Content-Length framing over the simulated socket stream.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_TCP_PORT) -> None:
        self._host = host
        self._port = port
        self._client_to_server: bytearray = bytearray()
        self._server_to_client: bytearray = bytearray()

    def send(self, message: LSPMessage) -> None:
        encoded = message.encode()
        self._server_to_client.extend(encoded.encode("utf-8"))

    def receive(self) -> Optional[LSPMessage]:
        if not self._client_to_server:
            return None
        raw = self._client_to_server.decode("utf-8")
        self._client_to_server.clear()
        try:
            return LSPMessage.decode(raw)
        except FizzLSPTransportError:
            return None

    def inject_client_message(self, raw: str) -> None:
        """Inject a raw message into the client-to-server buffer."""
        self._client_to_server.extend(raw.encode("utf-8"))

    def read_server_output(self) -> str:
        """Read and drain the server-to-client buffer."""
        data = self._server_to_client.decode("utf-8")
        self._server_to_client.clear()
        return data


class LSPDispatcher:
    """Routes incoming JSON-RPC messages to registered handler callables.

    Each handler is a callable that accepts a params dict and returns
    a result value (for requests) or None (for notifications).
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, Callable] = {}

    def register(self, method: str, handler: Callable) -> None:
        """Register a handler for a JSON-RPC method."""
        if method in self._handlers:
            raise FizzLSPDispatchError(method, "handler already registered")
        self._handlers[method] = handler

    def dispatch(self, message: LSPMessage) -> Optional[LSPMessage]:
        """Dispatch a message to its handler and return the response."""
        if message.method is None:
            return None

        handler = self._handlers.get(message.method)
        if handler is None:
            if message.id is not None:
                return LSPMessage(
                    id=message.id,
                    error={
                        "code": JSONRPC_METHOD_NOT_FOUND,
                        "message": f"Method not found: {message.method}",
                    },
                )
            return None

        try:
            result = handler(message.params or {})
        except FizzLSPError as e:
            if message.id is not None:
                return LSPMessage(
                    id=message.id,
                    error={
                        "code": JSONRPC_INTERNAL_ERROR,
                        "message": str(e),
                    },
                )
            return None
        except Exception as e:
            logger.exception("Handler error for %s", message.method)
            if message.id is not None:
                return LSPMessage(
                    id=message.id,
                    error={
                        "code": JSONRPC_INTERNAL_ERROR,
                        "message": f"Internal error: {e}",
                    },
                )
            return None

        # Notifications don't get responses
        if message.id is None:
            return None

        return LSPMessage(id=message.id, result=result)

    def _log_message(self, direction: str, message: LSPMessage) -> None:
        """Log message for protocol debugging."""
        logger.debug(
            "[%s] %s id=%s method=%s",
            direction,
            message.message_type.name,
            message.id,
            message.method,
        )


# ============================================================
# Document Synchronization
# ============================================================


class TextDocumentManager:
    """Manages the set of open documents.

    Documents are identified by URI and tracked through their full
    lifecycle: open, change, close.
    """

    def __init__(self) -> None:
        self._documents: Dict[str, TextDocumentItem] = {}

    def open_document(
        self, uri: str, language_id: str, version: int, text: str
    ) -> TextDocumentItem:
        """Create and store a new open document."""
        if uri in self._documents:
            raise FizzLSPDocumentError(uri, "document is already open")
        doc = TextDocumentItem(uri=uri, language_id=language_id, version=version, text=text)
        self._documents[uri] = doc
        return doc

    def update_document(
        self, uri: str, changes: List[Dict[str, Any]], version: int
    ) -> TextDocumentItem:
        """Apply incremental changes to an open document."""
        if uri not in self._documents:
            raise FizzLSPDocumentSyncError(uri, "document is not open")
        doc = self._documents[uri]
        if version <= doc.version:
            raise FizzLSPDocumentSyncError(
                uri, f"version {version} <= current version {doc.version}"
            )
        doc.text = IncrementalSyncEngine.apply_changes(doc.text, changes)
        doc.version = version
        return doc

    def close_document(self, uri: str) -> None:
        """Remove a document from the open set."""
        if uri not in self._documents:
            raise FizzLSPDocumentError(uri, "document is not open")
        del self._documents[uri]

    def get_document(self, uri: str) -> Optional[TextDocumentItem]:
        """Retrieve a document by URI."""
        return self._documents.get(uri)

    def all_documents(self) -> List[TextDocumentItem]:
        """Return all open documents."""
        return list(self._documents.values())

    def document_count(self) -> int:
        return len(self._documents)


class IncrementalSyncEngine:
    """Applies text edits to a document buffer.

    Handles incremental text synchronization as specified by LSP:
    each change has a range (start line/character to end line/character)
    and replacement text.
    """

    @staticmethod
    def apply_changes(text: str, changes: List[Dict[str, Any]]) -> str:
        """Apply each change in order to the document text."""
        for change in changes:
            if "range" not in change:
                # Full document replacement
                text = change.get("text", "")
                continue

            r = change["range"]
            start_line = r["start"]["line"]
            start_char = r["start"]["character"]
            end_line = r["end"]["line"]
            end_char = r["end"]["character"]
            new_text = change.get("text", "")

            line_starts = IncrementalSyncEngine._compute_line_starts(text)

            start_offset = IncrementalSyncEngine._position_to_offset(
                text, line_starts, start_line, start_char
            )
            end_offset = IncrementalSyncEngine._position_to_offset(
                text, line_starts, end_line, end_char
            )

            if start_offset > len(text) or end_offset > len(text):
                raise FizzLSPDocumentSyncError(
                    "unknown",
                    f"edit range ({start_line}:{start_char} to {end_line}:{end_char}) "
                    f"exceeds document boundary",
                )

            text = text[:start_offset] + new_text + text[end_offset:]

        return text

    @staticmethod
    def _compute_line_starts(text: str) -> List[int]:
        """Precompute the character offset of each line start."""
        starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                starts.append(i + 1)
        return starts

    @staticmethod
    def _position_to_offset(
        text: str, line_starts: List[int], line: int, character: int
    ) -> int:
        """Convert a line/character position to a character offset."""
        if line < 0 or line >= len(line_starts):
            # Clamp to document end
            return len(text)
        offset = line_starts[line] + character
        return min(offset, len(text))

    @staticmethod
    def _offset_to_position(text: str, offset: int) -> LSPPosition:
        """Convert a character offset to a line/character position."""
        line = 0
        col = 0
        for i, ch in enumerate(text):
            if i == offset:
                break
            if ch == "\n":
                line += 1
                col = 0
            else:
                col += 1
        return LSPPosition(line=line, character=col)


# ============================================================
# Analysis Pipeline
# ============================================================


class AnalysisPipeline:
    """Orchestrates four analysis passes on each document change.

    1. Lexical analysis (Lexer)
    2. Syntactic analysis (Parser)
    3. Semantic analysis (TypeChecker)
    4. Dependent type analysis (lightweight proof check)
    5. Symbol collection
    6. Semantic token classification
    """

    def __init__(self, dependent_type_diagnostics: bool = True) -> None:
        self._dependent_type_diagnostics = dependent_type_diagnostics

    def analyze(self, uri: str, source: str) -> AnalysisResult:
        """Run the full analysis pipeline on a document."""
        start = time.monotonic()
        result = AnalysisResult()
        tokens = []
        ast = None

        # Pass 1: Lexical analysis
        try:
            from enterprise_fizzbuzz.infrastructure.fizzlang import Lexer
            lexer = Lexer(source)
            lexer.tokenize()
            tokens = lexer.tokens
            result.tokens = tokens
        except Exception as e:
            diag = LSPDiagnostic(
                range=LSPRange(
                    start=LSPPosition(line=0, character=0),
                    end=LSPPosition(line=0, character=0),
                ),
                severity=DiagnosticSeverity.ERROR,
                code="EFP-FL11",
                message=str(e),
            )
            result.diagnostics.append(diag)

        # Pass 2: Syntactic analysis
        if tokens:
            try:
                from enterprise_fizzbuzz.infrastructure.fizzlang import Parser
                parser = Parser(tokens)
                ast = parser.parse()
                result.ast = ast
            except Exception as e:
                line_num = 0
                col_num = 0
                err_msg = str(e)
                # Try to extract line info from the error message
                import re as _re
                m = _re.search(r"line (\d+)", err_msg)
                if m:
                    line_num = max(0, int(m.group(1)) - 1)
                diag = LSPDiagnostic(
                    range=LSPRange(
                        start=LSPPosition(line=line_num, character=col_num),
                        end=LSPPosition(line=line_num, character=col_num),
                    ),
                    severity=DiagnosticSeverity.ERROR,
                    code="EFP-FL12",
                    message=err_msg,
                )
                result.diagnostics.append(diag)

        # Pass 3: Semantic analysis
        if ast is not None:
            try:
                from enterprise_fizzbuzz.infrastructure.fizzlang import TypeChecker
                checker = TypeChecker()
                checker.check(ast)
            except Exception as e:
                line_num = getattr(e, "line", 0)
                if isinstance(line_num, int) and line_num > 0:
                    line_num -= 1
                else:
                    line_num = 0
                diag = LSPDiagnostic(
                    range=LSPRange(
                        start=LSPPosition(line=line_num, character=0),
                        end=LSPPosition(line=line_num, character=0),
                    ),
                    severity=DiagnosticSeverity.ERROR,
                    code="EFP-FL13",
                    message=str(e),
                )
                result.diagnostics.append(diag)

        # Pass 4: Dependent type analysis
        if ast is not None and self._dependent_type_diagnostics:
            try:
                from enterprise_fizzbuzz.infrastructure.fizzlang import EvaluateNode
                for stmt in getattr(ast, "statements", []):
                    if isinstance(stmt, EvaluateNode):
                        diag = LSPDiagnostic(
                            range=LSPRange(
                                start=LSPPosition(line=getattr(stmt, "line", 1) - 1, character=0),
                                end=LSPPosition(line=getattr(stmt, "line", 1) - 1, character=0),
                            ),
                            severity=DiagnosticSeverity.INFORMATION,
                            code="EFP-LSP2",
                            message="Evaluate statement: proof obligation for range termination is trivially satisfied (finite integer bounds).",
                        )
                        result.diagnostics.append(diag)
            except Exception:
                pass

        # Pass 5: Symbol collection
        if ast is not None:
            result.symbol_table = self._collect_symbols(ast, tokens, uri)

        # Pass 6: Semantic token classification
        if tokens:
            result.semantic_tokens = self._classify_tokens(tokens, ast)

        # Empty source warning
        if not source.strip():
            diag = LSPDiagnostic(
                range=LSPRange(
                    start=LSPPosition(line=0, character=0),
                    end=LSPPosition(line=0, character=0),
                ),
                severity=DiagnosticSeverity.WARNING,
                code="EFP-LSP1",
                message="Empty FizzLang program. No rules, no evaluations, no purpose.",
            )
            result.diagnostics.append(diag)

        # Detect unused bindings
        self._detect_unused_bindings(result)

        result.analysis_time_ms = (time.monotonic() - start) * 1000
        return result

    def _collect_symbols(self, ast: Any, tokens: List, uri: str) -> SymbolTable:
        """Walk AST and collect symbols into a table."""
        from enterprise_fizzbuzz.infrastructure.fizzlang import (
            EvaluateNode,
            FunctionCallNode,
            IdentifierNode,
            LetNode,
            NVarNode,
            RuleNode,
        )

        table = SymbolTable()

        for stmt in getattr(ast, "statements", []):
            line = getattr(stmt, "line", 1) - 1  # Convert to 0-indexed

            if isinstance(stmt, RuleNode):
                loc = LSPLocation(
                    uri=uri,
                    range=LSPRange(
                        start=LSPPosition(line=line, character=5),  # after "rule "
                        end=LSPPosition(line=line, character=5 + len(stmt.name)),
                    ),
                )
                cond_str = self._node_to_string(stmt.condition) if stmt.condition else ""
                emit_str = self._node_to_string(stmt.emit_expr) if stmt.emit_expr else ""
                table.add_symbol(SymbolInfo(
                    name=stmt.name,
                    kind="rule",
                    definition_location=loc,
                    type_info=f"(int) -> bool",
                    documentation=f"Rule: when {cond_str} emit {emit_str} priority {stmt.priority}",
                ))

            elif isinstance(stmt, LetNode):
                loc = LSPLocation(
                    uri=uri,
                    range=LSPRange(
                        start=LSPPosition(line=line, character=4),  # after "let "
                        end=LSPPosition(line=line, character=4 + len(stmt.name)),
                    ),
                )
                type_info = _infer_type(stmt.value) if stmt.value else "unknown"
                table.add_symbol(SymbolInfo(
                    name=stmt.name,
                    kind="variable",
                    definition_location=loc,
                    type_info=type_info,
                    documentation=f"let {stmt.name} = {self._node_to_string(stmt.value)}",
                ))

        # Collect references by walking the AST
        self._walk_for_references(ast, table, uri)

        # Add stdlib function symbols
        for fn_name in _STDLIB_FUNCTIONS:
            fn_types = {"is_prime": "(int) -> bool", "fizzbuzz": "(int) -> string", "range": "(int, int) -> list"}
            fn_docs = {
                "is_prime": "Trial-division primality test. Returns true if n is prime.",
                "fizzbuzz": "Evaluate standard FizzBuzz for a single number. Returns the classification string.",
                "range": "Return integers from a to b inclusive.",
            }
            table.add_symbol(SymbolInfo(
                name=fn_name,
                kind="function",
                definition_location=LSPLocation(
                    uri="builtin:///fizzlang/stdlib",
                    range=LSPRange(
                        start=LSPPosition(line=0, character=0),
                        end=LSPPosition(line=0, character=len(fn_name)),
                    ),
                ),
                type_info=fn_types.get(fn_name, "unknown"),
                documentation=fn_docs.get(fn_name, ""),
            ))

        return table

    def _walk_for_references(self, node: Any, table: SymbolTable, uri: str) -> None:
        """Recursively walk AST collecting references for symbols."""
        from enterprise_fizzbuzz.infrastructure.fizzlang import (
            BinaryOpNode,
            EvaluateNode,
            FunctionCallNode,
            IdentifierNode,
            LetNode,
            NVarNode,
            ProgramNode,
            RuleNode,
            UnaryOpNode,
        )

        if node is None:
            return

        if isinstance(node, IdentifierNode):
            info = table.get_symbol(node.name)
            if info:
                loc = LSPLocation(
                    uri=uri,
                    range=LSPRange(
                        start=LSPPosition(line=getattr(node, "line", 1) - 1, character=0),
                        end=LSPPosition(line=getattr(node, "line", 1) - 1, character=len(node.name)),
                    ),
                )
                info.references.append(loc)

        elif isinstance(node, FunctionCallNode):
            info = table.get_symbol(node.name)
            if info:
                loc = LSPLocation(
                    uri=uri,
                    range=LSPRange(
                        start=LSPPosition(line=getattr(node, "line", 1) - 1, character=0),
                        end=LSPPosition(line=getattr(node, "line", 1) - 1, character=len(node.name)),
                    ),
                )
                info.references.append(loc)
            for arg in node.args:
                self._walk_for_references(arg, table, uri)

        elif isinstance(node, ProgramNode):
            for stmt in node.statements:
                self._walk_for_references(stmt, table, uri)

        elif isinstance(node, RuleNode):
            self._walk_for_references(node.condition, table, uri)
            self._walk_for_references(node.emit_expr, table, uri)

        elif isinstance(node, LetNode):
            self._walk_for_references(node.value, table, uri)

        elif isinstance(node, EvaluateNode):
            self._walk_for_references(node.start, table, uri)
            self._walk_for_references(node.end, table, uri)

        elif isinstance(node, BinaryOpNode):
            self._walk_for_references(node.left, table, uri)
            self._walk_for_references(node.right, table, uri)

        elif isinstance(node, UnaryOpNode):
            self._walk_for_references(node.operand, table, uri)

    def _classify_tokens(self, tokens: List, ast: Any) -> List[Tuple[int, int, int, int, int]]:
        """Classify each token for semantic highlighting."""
        from enterprise_fizzbuzz.infrastructure.fizzlang import TokenType

        semantic_data: List[SemanticTokenData] = []

        # Build a set of declaration names from the AST for modifier tracking
        rule_names: Set[str] = set()
        var_names: Set[str] = set()
        if ast is not None:
            from enterprise_fizzbuzz.infrastructure.fizzlang import LetNode, RuleNode
            for stmt in getattr(ast, "statements", []):
                if isinstance(stmt, RuleNode):
                    rule_names.add(stmt.name)
                elif isinstance(stmt, LetNode):
                    var_names.add(stmt.name)

        for tok in tokens:
            token_type = tok.type
            line = tok.line - 1  # Convert to 0-indexed
            col = tok.col - 1

            if token_type == TokenType.EOF or token_type == TokenType.NEWLINE:
                continue

            length = len(str(tok.value)) if tok.value is not None else 1
            if token_type == TokenType.STRING:
                length = len(tok.value) + 2  # Include quotes

            st = None
            modifiers = 0

            # Keywords
            if token_type in (
                TokenType.RULE, TokenType.WHEN, TokenType.EMIT,
                TokenType.EVALUATE, TokenType.TO, TokenType.LET,
                TokenType.PRIORITY, TokenType.AND, TokenType.OR,
                TokenType.NOT, TokenType.TRUE, TokenType.FALSE,
            ):
                st = SemanticTokenType.KEYWORD

            # The sacred variable n
            elif token_type == TokenType.N_VAR:
                st = SemanticTokenType.VARIABLE
                modifiers = 1 << SemanticTokenModifier.READONLY.value

            # Identifiers
            elif token_type == TokenType.IDENTIFIER:
                name = tok.value
                if name in rule_names:
                    st = SemanticTokenType.FUNCTION
                    modifiers = 1 << SemanticTokenModifier.DECLARATION.value
                elif name in var_names:
                    st = SemanticTokenType.VARIABLE
                elif name in _STDLIB_FUNCTIONS:
                    st = SemanticTokenType.FUNCTION
                    modifiers = 1 << SemanticTokenModifier.DEFAULT_LIBRARY.value
                else:
                    st = SemanticTokenType.VARIABLE

            # Literals
            elif token_type == TokenType.INTEGER:
                st = SemanticTokenType.NUMBER
            elif token_type == TokenType.STRING:
                st = SemanticTokenType.STRING

            # Operators
            elif token_type in (
                TokenType.PLUS, TokenType.MINUS, TokenType.STAR,
                TokenType.SLASH, TokenType.PERCENT, TokenType.EQUALS,
                TokenType.NOT_EQUALS, TokenType.LESS_THAN,
                TokenType.GREATER_THAN, TokenType.LESS_EQUAL,
                TokenType.GREATER_EQUAL, TokenType.ASSIGN,
            ):
                st = SemanticTokenType.OPERATOR

            if st is not None:
                semantic_data.append(SemanticTokenData(
                    line=line,
                    start_char=col,
                    length=length,
                    token_type=st,
                    modifiers=modifiers,
                ))

        # Delta-encode
        return self._delta_encode(semantic_data)

    def _delta_encode(self, tokens: List[SemanticTokenData]) -> List[Tuple[int, int, int, int, int]]:
        """Sort tokens and produce delta-encoded 5-tuples."""
        tokens.sort(key=lambda t: (t.line, t.start_char))
        encoded = []
        prev_line = 0
        prev_char = 0
        for t in tokens:
            delta_line = t.line - prev_line
            delta_char = t.start_char - (prev_char if delta_line == 0 else 0)
            encoded.append((delta_line, delta_char, t.length, t.token_type.value, t.modifiers))
            prev_line = t.line
            prev_char = t.start_char
        return encoded

    def _detect_unused_bindings(self, result: AnalysisResult) -> None:
        """Add HINT diagnostics for let-bindings with zero references."""
        for info in result.symbol_table.all_variables():
            if not info.references and info.kind == "variable":
                diag = LSPDiagnostic(
                    range=info.definition_location.range,
                    severity=DiagnosticSeverity.HINT,
                    code="EFP-LSP1",
                    message=f"Variable '{info.name}' is declared but never referenced.",
                    tags=[DiagnosticTag.UNNECESSARY],
                )
                result.diagnostics.append(diag)

    def _node_to_string(self, node: Any) -> str:
        """Convert an AST node to its string representation."""
        from enterprise_fizzbuzz.infrastructure.fizzlang import (
            BinaryOpNode,
            FunctionCallNode,
            IdentifierNode,
            LiteralNode,
            NVarNode,
            UnaryOpNode,
        )

        if node is None:
            return ""
        if isinstance(node, LiteralNode):
            if isinstance(node.value, str):
                return f'"{node.value}"'
            return str(node.value)
        if isinstance(node, NVarNode):
            return "n"
        if isinstance(node, IdentifierNode):
            return node.name
        if isinstance(node, BinaryOpNode):
            left = self._node_to_string(node.left)
            right = self._node_to_string(node.right)
            return f"{left} {node.op} {right}"
        if isinstance(node, UnaryOpNode):
            operand = self._node_to_string(node.operand)
            return f"{node.op} {operand}"
        if isinstance(node, FunctionCallNode):
            args = ", ".join(self._node_to_string(a) for a in node.args)
            return f"{node.name}({args})"
        return str(node)


# ============================================================
# Completion Provider
# ============================================================


class CompletionProvider:
    """Implements textDocument/completion.

    Determines completion context by analyzing cursor position relative
    to the token stream and partial AST, then delegates to the appropriate
    context-specific completion method.
    """

    def __init__(self, max_items: int = DEFAULT_MAX_COMPLETION_ITEMS) -> None:
        self._max_items = max_items

    def complete(
        self,
        uri: str,
        position: LSPPosition,
        context: Dict[str, Any],
        analysis: Optional[AnalysisResult] = None,
        source: str = "",
    ) -> List[CompletionItem]:
        """Compute completion items at the given cursor position."""
        tokens = analysis.tokens if analysis else []
        symbol_table = analysis.symbol_table if analysis else SymbolTable()

        # Determine context
        ctx = self._determine_context(tokens, position, uri, source)

        items: List[CompletionItem] = []

        if ctx == "statement":
            items.extend(self._complete_statement_level())
        elif ctx.startswith("keyword_after_"):
            items.extend(self._complete_keyword_sequence(ctx))
        elif ctx == "expression":
            items.extend(self._complete_variables(symbol_table, position))
            items.extend(self._complete_functions())
            items.extend(self._complete_operators())
        elif ctx == "fizzfile":
            items.extend(self._complete_fizzfile())
        elif ctx == "fizzgrammar":
            items.extend(self._complete_fizzgrammar())
        else:
            # Default: offer everything
            items.extend(self._complete_statement_level())
            items.extend(self._complete_variables(symbol_table, position))
            items.extend(self._complete_functions())

        return items[:self._max_items]

    def resolve(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Lazily resolve additional details for a completion item."""
        data = item.get("data", {})
        kind = data.get("kind", "")
        if kind == "function":
            name = item.get("label", "")
            docs = {
                "is_prime": "Trial-division primality test. O(sqrt(n)) because correctness demands it.\n\nArity: 1",
                "fizzbuzz": "Evaluate standard FizzBuzz for a single number.\n\nArity: 1",
                "range": "Return integers from a to b inclusive.\n\nArity: 2",
            }
            item["documentation"] = docs.get(name, "")
        return item

    def _determine_context(
        self, tokens: List, position: LSPPosition, uri: str, source: str
    ) -> str:
        """Analyze preceding tokens to determine completion context."""
        if uri.endswith(".fizzfile"):
            return "fizzfile"
        if uri.endswith(".fizzgrammar"):
            return "fizzgrammar"
        if source.lstrip().startswith("::=") or "::=" in source[:100]:
            return "fizzgrammar"

        from enterprise_fizzbuzz.infrastructure.fizzlang import TokenType

        # Find tokens before cursor
        preceding = []
        for tok in tokens:
            tok_line = tok.line - 1
            tok_col = tok.col - 1
            if tok.type == TokenType.EOF:
                continue
            if tok_line < position.line or (tok_line == position.line and tok_col < position.character):
                preceding.append(tok)

        if not preceding:
            return "statement"

        last = preceding[-1]

        # After a rule name identifier, suggest 'when'
        if len(preceding) >= 2:
            second_last = preceding[-2]
            if second_last.type == TokenType.RULE and last.type == TokenType.IDENTIFIER:
                return "keyword_after_rule"

        if last.type == TokenType.RULE:
            return "expression"  # Need rule name first

        # After keyword sequences
        if last.type == TokenType.WHEN:
            return "expression"
        if last.type == TokenType.EMIT:
            return "expression"
        if last.type == TokenType.EVALUATE:
            return "expression"

        # Check for 'when EXPR' -> suggest 'emit'
        for i in range(len(preceding) - 1, -1, -1):
            if preceding[i].type == TokenType.WHEN:
                # Check if we're past the condition expression
                if i < len(preceding) - 1:
                    return "keyword_after_when"
                break
            if preceding[i].type == TokenType.EMIT:
                return "keyword_after_emit"
            if preceding[i].type == TokenType.EVALUATE:
                if i < len(preceding) - 1:
                    return "keyword_after_evaluate"
                break

        # At newline or start of line -> statement level
        if last.type == TokenType.NEWLINE:
            return "statement"

        return "expression"

    def _complete_statement_level(self) -> List[CompletionItem]:
        """Statement-level completions: rule, let, evaluate."""
        return [
            CompletionItem(
                label="rule",
                kind=CompletionItemKind.KEYWORD,
                detail="Declare a FizzBuzz classification rule",
                insert_text="rule ${1:name} when ${2:condition} emit ${3:expression} priority ${4:0}",
                insert_text_format=InsertTextFormat.SNIPPET,
                sort_text="0rule",
            ),
            CompletionItem(
                label="let",
                kind=CompletionItemKind.KEYWORD,
                detail="Bind a value to a name",
                insert_text="let ${1:name} = ${2:expression}",
                insert_text_format=InsertTextFormat.SNIPPET,
                sort_text="0let",
            ),
            CompletionItem(
                label="evaluate",
                kind=CompletionItemKind.KEYWORD,
                detail="Evaluate a range of numbers",
                insert_text="evaluate ${1:start} to ${2:end}",
                insert_text_format=InsertTextFormat.SNIPPET,
                sort_text="0evaluate",
            ),
        ]

    def _complete_keyword_sequence(self, ctx: str) -> List[CompletionItem]:
        """Context-specific keyword completions within a statement."""
        if ctx == "keyword_after_rule":
            return [CompletionItem(
                label="when",
                kind=CompletionItemKind.KEYWORD,
                detail="Condition clause",
                sort_text="0when",
            )]
        if ctx == "keyword_after_when":
            return [CompletionItem(
                label="emit",
                kind=CompletionItemKind.KEYWORD,
                detail="Output expression clause",
                sort_text="0emit",
            )]
        if ctx == "keyword_after_emit":
            return [CompletionItem(
                label="priority",
                kind=CompletionItemKind.KEYWORD,
                detail="Rule priority clause",
                sort_text="0priority",
            )]
        if ctx == "keyword_after_evaluate":
            return [CompletionItem(
                label="to",
                kind=CompletionItemKind.KEYWORD,
                detail="Range end clause",
                sort_text="0to",
            )]
        return []

    def _complete_variables(
        self, symbol_table: SymbolTable, position: LSPPosition
    ) -> List[CompletionItem]:
        """Variable completions: let-bound variables and n."""
        items = [
            CompletionItem(
                label="n",
                kind=CompletionItemKind.VARIABLE,
                detail="int",
                documentation="The number being evaluated.",
                sort_text="1n",
            ),
            CompletionItem(
                label="true",
                kind=CompletionItemKind.KEYWORD,
                detail="bool",
                sort_text="1true",
            ),
            CompletionItem(
                label="false",
                kind=CompletionItemKind.KEYWORD,
                detail="bool",
                sort_text="1false",
            ),
        ]
        for info in symbol_table.all_variables():
            items.append(CompletionItem(
                label=info.name,
                kind=CompletionItemKind.VARIABLE,
                detail=info.type_info,
                documentation=info.documentation,
                sort_text=f"1{info.name}",
            ))
        return items

    def _complete_functions(self) -> List[CompletionItem]:
        """Stdlib function completions with signatures and documentation."""
        return [
            CompletionItem(
                label="is_prime",
                kind=CompletionItemKind.FUNCTION,
                detail="(int) -> bool",
                documentation="Trial-division primality test. Returns true if n is prime.",
                insert_text="is_prime(${1:n})",
                insert_text_format=InsertTextFormat.SNIPPET,
                sort_text="2is_prime",
                data={"kind": "function"},
            ),
            CompletionItem(
                label="fizzbuzz",
                kind=CompletionItemKind.FUNCTION,
                detail="(int) -> string",
                documentation="Evaluate standard FizzBuzz for a single number. Returns the classification string.",
                insert_text="fizzbuzz(${1:n})",
                insert_text_format=InsertTextFormat.SNIPPET,
                sort_text="2fizzbuzz",
                data={"kind": "function"},
            ),
            CompletionItem(
                label="range",
                kind=CompletionItemKind.FUNCTION,
                detail="(int, int) -> list",
                documentation="Return integers from a to b inclusive.",
                insert_text="range(${1:a}, ${2:b})",
                insert_text_format=InsertTextFormat.SNIPPET,
                sort_text="2range",
                data={"kind": "function"},
            ),
        ]

    def _complete_operators(self) -> List[CompletionItem]:
        """Operator completions."""
        ops = [
            ("+", "Addition"), ("-", "Subtraction"), ("*", "Multiplication"),
            ("/", "Division"), ("%", "Modulo (remainder)"),
            ("==", "Equality"), ("!=", "Inequality"),
            ("<", "Less than"), (">", "Greater than"),
            ("<=", "Less or equal"), (">=", "Greater or equal"),
            ("and", "Logical AND"), ("or", "Logical OR"),
        ]
        return [
            CompletionItem(
                label=op,
                kind=CompletionItemKind.OPERATOR,
                detail=desc,
                sort_text=f"3{op}",
            )
            for op, desc in ops
        ]

    def _complete_fizzfile(self) -> List[CompletionItem]:
        """Fizzfile directive completions."""
        directives = [
            "FROM", "FIZZ", "BUZZ", "RUN", "COPY", "ENV", "ENTRYPOINT",
            "LABEL", "EXPOSE", "VOLUME", "WORKDIR", "USER", "HEALTHCHECK",
        ]
        return [
            CompletionItem(
                label=d,
                kind=CompletionItemKind.KEYWORD,
                detail=f"Fizzfile directive: {d}",
                sort_text=f"0{d}",
            )
            for d in directives
        ]

    def _complete_fizzgrammar(self) -> List[CompletionItem]:
        """FizzGrammar BNF completions."""
        items = ["::=", "|", ";", "IDENTIFIER", "NUMBER", "STRING"]
        return [
            CompletionItem(
                label=i,
                kind=CompletionItemKind.KEYWORD,
                detail=f"Grammar symbol: {i}",
                sort_text=f"0{i}",
            )
            for i in items
        ]


# ============================================================
# Diagnostic Provider
# ============================================================


class DiagnosticPublisher:
    """Converts AnalysisResult diagnostics into LSP publishDiagnostics notifications."""

    def publish(self, uri: str, diagnostics: List[LSPDiagnostic]) -> LSPMessage:
        """Construct a textDocument/publishDiagnostics notification."""
        return LSPMessage(
            method="textDocument/publishDiagnostics",
            params={
                "uri": uri,
                "diagnostics": [self._serialize_diagnostic(d) for d in diagnostics],
            },
        )

    def clear(self, uri: str) -> LSPMessage:
        """Publish empty diagnostics to clear all markers for a URI."""
        return LSPMessage(
            method="textDocument/publishDiagnostics",
            params={"uri": uri, "diagnostics": []},
        )

    def _serialize_diagnostic(self, diag: LSPDiagnostic) -> Dict[str, Any]:
        """Convert a diagnostic to LSP wire format."""
        d: Dict[str, Any] = {
            "range": {
                "start": {"line": diag.range.start.line, "character": diag.range.start.character},
                "end": {"line": diag.range.end.line, "character": diag.range.end.character},
            },
            "severity": diag.severity.value,
            "code": diag.code,
            "source": diag.source,
            "message": diag.message,
        }
        if diag.related_information:
            d["relatedInformation"] = diag.related_information
        if diag.tags:
            d["tags"] = [t.value for t in diag.tags]
        return d

    def _add_related_info(
        self,
        diag: LSPDiagnostic,
        symbol_table: SymbolTable,
    ) -> None:
        """Add related information for diagnostics that benefit from it."""
        if "undefined" in diag.message.lower():
            # Extract the undefined name
            import re as _re
            m = _re.search(r"'(\w+)'", diag.message)
            if m:
                name = m.group(1)
                similar = symbol_table.find_similar_name(name)
                if similar:
                    info = symbol_table.get_symbol(similar)
                    if info:
                        diag.related_information.append({
                            "location": {
                                "uri": info.definition_location.uri,
                                "range": {
                                    "start": {
                                        "line": info.definition_location.range.start.line,
                                        "character": info.definition_location.range.start.character,
                                    },
                                    "end": {
                                        "line": info.definition_location.range.end.line,
                                        "character": info.definition_location.range.end.character,
                                    },
                                },
                            },
                            "message": f"Did you mean '{similar}'?",
                        })


class DiagnosticThrottler:
    """Debounces diagnostic publication.

    Multiple rapid document changes within the debounce window produce
    only a single diagnostic publication, reducing noise during active
    typing.
    """

    def __init__(self, debounce_ms: int = DEFAULT_DIAGNOSTIC_DEBOUNCE_MS) -> None:
        self._debounce_ms = debounce_ms
        self._pending: Dict[str, Tuple[float, Callable]] = {}

    def schedule(self, uri: str, callback: Callable) -> None:
        """Schedule a diagnostic publication.  Cancels any pending callback for this URI."""
        self._pending[uri] = (time.monotonic(), callback)

    def flush(self, uri: str) -> None:
        """Immediately execute the pending callback for a URI."""
        if uri in self._pending:
            _, callback = self._pending.pop(uri)
            callback()

    def flush_all(self) -> None:
        """Execute all pending callbacks."""
        for uri in list(self._pending.keys()):
            self.flush(uri)

    def has_pending(self, uri: str) -> bool:
        return uri in self._pending


# ============================================================
# Definition Provider
# ============================================================


class DefinitionProvider:
    """Implements textDocument/definition.

    Identifies the symbol under the cursor and returns its definition
    location in the source.
    """

    def definition(
        self,
        uri: str,
        position: LSPPosition,
        symbol_table: SymbolTable,
        ast: Any,
        tokens: List,
    ) -> Optional[LSPLocation]:
        """Resolve the definition location for the symbol at cursor."""
        token = self._find_token_at_position(tokens, position)
        if token is None:
            return None

        kind = self._classify_token_for_definition(token, ast, symbol_table)

        if kind == "variable":
            return self._resolve_variable(token.value, symbol_table)
        if kind == "rule":
            return self._resolve_rule(token.value, symbol_table)
        if kind == "function":
            return self._resolve_stdlib_function(token.value, symbol_table)
        if kind == "n":
            return None  # n has no definition site
        if kind == "keyword":
            return None

        return None

    def _resolve_variable(self, name: str, symbol_table: SymbolTable) -> Optional[LSPLocation]:
        info = symbol_table.get_symbol(name)
        if info and info.kind == "variable":
            return info.definition_location
        return None

    def _resolve_rule(self, name: str, symbol_table: SymbolTable) -> Optional[LSPLocation]:
        info = symbol_table.get_symbol(name)
        if info and info.kind == "rule":
            return info.definition_location
        return None

    def _resolve_stdlib_function(self, name: str, symbol_table: SymbolTable) -> Optional[LSPLocation]:
        info = symbol_table.get_symbol(name)
        if info and info.kind == "function":
            return info.definition_location
        return None

    def _find_token_at_position(self, tokens: List, position: LSPPosition) -> Any:
        """Find the token whose source range contains the cursor position."""
        from enterprise_fizzbuzz.infrastructure.fizzlang import TokenType

        for tok in tokens:
            if tok.type == TokenType.EOF or tok.type == TokenType.NEWLINE:
                continue
            tok_line = tok.line - 1
            tok_col = tok.col - 1
            tok_len = len(str(tok.value)) if tok.value is not None else 1
            if tok.type == TokenType.STRING:
                tok_len = len(tok.value) + 2

            if (tok_line == position.line and
                    tok_col <= position.character < tok_col + tok_len):
                return tok
        return None

    def _classify_token_for_definition(self, token: Any, ast: Any, symbol_table: SymbolTable) -> str:
        """Determine what kind of entity a token represents."""
        from enterprise_fizzbuzz.infrastructure.fizzlang import TokenType

        if token.type == TokenType.N_VAR:
            return "n"

        if token.type == TokenType.IDENTIFIER:
            name = token.value
            info = symbol_table.get_symbol(name)
            if info:
                return info.kind
            if name in _STDLIB_FUNCTIONS:
                return "function"
            return "variable"

        if token.type in (
            TokenType.RULE, TokenType.WHEN, TokenType.EMIT,
            TokenType.EVALUATE, TokenType.TO, TokenType.LET,
            TokenType.PRIORITY, TokenType.AND, TokenType.OR,
            TokenType.NOT, TokenType.TRUE, TokenType.FALSE,
        ):
            return "keyword"

        return "unknown"


# ============================================================
# Hover Provider
# ============================================================


class HoverProvider:
    """Implements textDocument/hover.

    Identifies the entity under the cursor and returns Markdown hover
    content with type information, documentation, and for integer
    literals, the FizzBuzz classification.
    """

    def hover(
        self,
        uri: str,
        position: LSPPosition,
        symbol_table: SymbolTable,
        ast: Any,
        tokens: List,
    ) -> Optional[Dict[str, Any]]:
        """Generate hover content for the entity at cursor."""
        token = DefinitionProvider()._find_token_at_position(tokens, position)
        if token is None:
            return None

        from enterprise_fizzbuzz.infrastructure.fizzlang import TokenType

        content = None

        if token.type == TokenType.N_VAR:
            content = self._hover_n()
        elif token.type == TokenType.IDENTIFIER:
            name = token.value
            info = symbol_table.get_symbol(name)
            if info:
                if info.kind == "variable":
                    content = self._hover_variable(name, symbol_table)
                elif info.kind == "rule":
                    content = self._hover_rule(name, symbol_table, ast)
                elif info.kind == "function":
                    content = self._hover_stdlib_function(name)
            elif name in _STDLIB_FUNCTIONS:
                content = self._hover_stdlib_function(name)
        elif token.type == TokenType.INTEGER:
            content = self._hover_integer_literal(token.value)
        elif token.type == TokenType.STRING:
            content = f"(`literal`) \"{token.value}\": string"
        elif token.type in (
            TokenType.RULE, TokenType.WHEN, TokenType.EMIT,
            TokenType.EVALUATE, TokenType.TO, TokenType.LET,
            TokenType.PRIORITY, TokenType.AND, TokenType.OR,
            TokenType.NOT, TokenType.TRUE, TokenType.FALSE,
        ):
            content = self._hover_keyword(token.value if isinstance(token.value, str) else token.type.name.lower())
        elif token.type in (
            TokenType.PLUS, TokenType.MINUS, TokenType.STAR,
            TokenType.SLASH, TokenType.PERCENT, TokenType.EQUALS,
            TokenType.NOT_EQUALS, TokenType.LESS_THAN,
            TokenType.GREATER_THAN, TokenType.LESS_EQUAL,
            TokenType.GREATER_EQUAL,
        ):
            content = self._hover_operator(str(token.value))

        if content is None:
            return None

        return {
            "contents": {"kind": "markdown", "value": content},
        }

    def _hover_variable(self, name: str, symbol_table: SymbolTable) -> str:
        info = symbol_table.get_symbol(name)
        if not info:
            return f"(`variable`) {name}: unknown"
        return f"(`variable`) {name}: {info.type_info}\n\n{info.documentation}"

    def _hover_n(self) -> str:
        return (
            "(`intrinsic`) n: int\n\n"
            "The number being evaluated. The only value that matters in FizzBuzz. "
            "All other variables exist in service of `n`."
        )

    def _hover_stdlib_function(self, name: str) -> str:
        sigs = {
            "is_prime": "(`function`) is_prime(n: int) -> bool\n\nTrial-division primality test. O(sqrt(n)) because correctness demands it.\n\nArity: 1",
            "fizzbuzz": "(`function`) fizzbuzz(n: int) -> string\n\nEvaluate standard FizzBuzz for a single number. Returns the classification string.\n\nArity: 1",
            "range": "(`function`) range(a: int, b: int) -> list\n\nReturn integers from a to b inclusive.\n\nArity: 2",
        }
        return sigs.get(name, f"(`function`) {name}(...)")

    def _hover_rule(self, name: str, symbol_table: SymbolTable, ast: Any) -> str:
        info = symbol_table.get_symbol(name)
        if not info:
            return f"(`rule`) {name}"
        return f"(`rule`) {name}\n\n{info.documentation}"

    def _hover_keyword(self, keyword: str) -> str:
        kw = keyword.lower()
        docs = {
            "rule": "Declares a FizzBuzz classification rule. Syntax: `rule NAME when CONDITION emit EXPRESSION [priority N]`",
            "let": "Binds a value to a name. Syntax: `let NAME = EXPRESSION`",
            "evaluate": "Evaluates a range of numbers through the declared rules. Syntax: `evaluate START to END`",
            "when": "Introduces the condition clause of a rule.",
            "emit": "Introduces the output expression of a rule.",
            "priority": "Sets the priority of a rule. Higher priority rules are evaluated first.",
            "to": "Separates the start and end of an evaluate range.",
            "and": "Logical conjunction. Both operands must be true.",
            "or": "Logical disjunction. At least one operand must be true.",
            "not": "Logical negation. Inverts the truth value.",
            "true": "Boolean literal: true.",
            "false": "Boolean literal: false.",
        }
        return f"(`keyword`) {kw}\n\n{docs.get(kw, '')}"

    def _hover_operator(self, op: str) -> str:
        docs = {
            "%": "Modulo operator. Returns the remainder of integer division. The single most important operator in FizzBuzz.",
            "+": "Addition operator. Returns the sum of two integers.",
            "-": "Subtraction operator. Returns the difference of two integers.",
            "*": "Multiplication operator. Returns the product of two integers.",
            "/": "Division operator. Returns the integer quotient.",
            "==": "Equality comparison. Returns `true` if both operands are equal.",
            "!=": "Inequality comparison. Returns `true` if operands differ.",
            "<": "Less-than comparison.",
            ">": "Greater-than comparison.",
            "<=": "Less-or-equal comparison.",
            ">=": "Greater-or-equal comparison.",
        }
        return f"(`operator`) {op}\n\n{docs.get(op, 'Operator.')}"

    def _hover_integer_literal(self, value: int) -> str:
        # Actually classify the number
        if value % 15 == 0:
            classification = "FizzBuzz"
        elif value % 3 == 0:
            classification = "Fizz"
        elif value % 5 == 0:
            classification = "Buzz"
        else:
            classification = str(value)
        return f"(`literal`) {value}: int\n\nFizzBuzz classification: {classification}"


# ============================================================
# References Provider
# ============================================================


class ReferencesProvider:
    """Implements textDocument/references.

    Collects all locations referencing the symbol at the cursor position.
    """

    def references(
        self,
        uri: str,
        position: LSPPosition,
        include_declaration: bool,
        symbol_table: SymbolTable,
        ast: Any,
        tokens: List,
        source: str = "",
    ) -> List[LSPLocation]:
        """Find all references to the symbol at cursor."""
        token = DefinitionProvider()._find_token_at_position(tokens, position)
        if token is None:
            return []

        from enterprise_fizzbuzz.infrastructure.fizzlang import TokenType

        if token.type == TokenType.N_VAR:
            return self._collect_n_refs(ast, uri)

        if token.type != TokenType.IDENTIFIER:
            return []

        name = token.value
        info = symbol_table.get_symbol(name)
        if not info:
            return []

        if info.kind == "variable":
            return self._collect_variable_refs(name, symbol_table, uri, include_declaration)
        if info.kind == "rule":
            return self._collect_rule_refs(name, symbol_table, tokens, uri, include_declaration, source)
        if info.kind == "function":
            return self._collect_function_refs(name, symbol_table, uri, include_declaration)

        return []

    def _collect_variable_refs(
        self, name: str, symbol_table: SymbolTable, uri: str, include_declaration: bool
    ) -> List[LSPLocation]:
        info = symbol_table.get_symbol(name)
        if not info:
            return []
        refs = list(info.references)
        if include_declaration:
            refs.insert(0, info.definition_location)
        return refs

    def _collect_rule_refs(
        self, name: str, symbol_table: SymbolTable, tokens: List, uri: str,
        include_declaration: bool, source: str
    ) -> List[LSPLocation]:
        info = symbol_table.get_symbol(name)
        if not info:
            return []
        refs = list(info.references)
        if include_declaration:
            refs.insert(0, info.definition_location)
        # Also scan comments for references
        self._scan_comments_for_refs(name, source, uri, refs)
        return refs

    def _collect_function_refs(
        self, name: str, symbol_table: SymbolTable, uri: str, include_declaration: bool
    ) -> List[LSPLocation]:
        info = symbol_table.get_symbol(name)
        if not info:
            return []
        refs = list(info.references)
        if include_declaration:
            refs.insert(0, info.definition_location)
        return refs

    def _collect_n_refs(self, ast: Any, uri: str) -> List[LSPLocation]:
        """Collect all NVarNode references."""
        from enterprise_fizzbuzz.infrastructure.fizzlang import NVarNode
        refs: List[LSPLocation] = []
        self._walk_for_n(ast, uri, refs)
        return refs

    def _walk_for_n(self, node: Any, uri: str, refs: List[LSPLocation]) -> None:
        from enterprise_fizzbuzz.infrastructure.fizzlang import (
            BinaryOpNode,
            EvaluateNode,
            FunctionCallNode,
            LetNode,
            NVarNode,
            ProgramNode,
            RuleNode,
            UnaryOpNode,
        )

        if node is None:
            return
        if isinstance(node, NVarNode):
            refs.append(LSPLocation(
                uri=uri,
                range=LSPRange(
                    start=LSPPosition(line=getattr(node, "line", 1) - 1, character=0),
                    end=LSPPosition(line=getattr(node, "line", 1) - 1, character=1),
                ),
            ))
        elif isinstance(node, ProgramNode):
            for stmt in node.statements:
                self._walk_for_n(stmt, uri, refs)
        elif isinstance(node, RuleNode):
            self._walk_for_n(node.condition, uri, refs)
            self._walk_for_n(node.emit_expr, uri, refs)
        elif isinstance(node, LetNode):
            self._walk_for_n(node.value, uri, refs)
        elif isinstance(node, EvaluateNode):
            self._walk_for_n(node.start, uri, refs)
            self._walk_for_n(node.end, uri, refs)
        elif isinstance(node, BinaryOpNode):
            self._walk_for_n(node.left, uri, refs)
            self._walk_for_n(node.right, uri, refs)
        elif isinstance(node, UnaryOpNode):
            self._walk_for_n(node.operand, uri, refs)
        elif isinstance(node, FunctionCallNode):
            for arg in node.args:
                self._walk_for_n(arg, uri, refs)

    def _scan_comments_for_refs(
        self, name: str, source: str, uri: str, refs: List[LSPLocation]
    ) -> None:
        """Scan source comments for word-boundary references to a name."""
        for i, line in enumerate(source.split("\n")):
            stripped = line.strip()
            if stripped.startswith("#"):
                pattern = rf"\b{re.escape(name)}\b"
                for m in re.finditer(pattern, stripped):
                    refs.append(LSPLocation(
                        uri=uri,
                        range=LSPRange(
                            start=LSPPosition(line=i, character=line.index("#") + m.start()),
                            end=LSPPosition(line=i, character=line.index("#") + m.end()),
                        ),
                    ))


# ============================================================
# Rename Provider
# ============================================================


class RenameProvider:
    """Implements textDocument/rename and textDocument/prepareRename.

    Validates renameability, checks for conflicts, and computes all
    necessary text edits across the document.
    """

    def prepare_rename(
        self,
        uri: str,
        position: LSPPosition,
        symbol_table: SymbolTable,
        tokens: List,
    ) -> Optional[Dict[str, Any]]:
        """Validate that the symbol at cursor is renameable."""
        token = DefinitionProvider()._find_token_at_position(tokens, position)
        if token is None:
            return None

        from enterprise_fizzbuzz.infrastructure.fizzlang import TokenType

        if token.type == TokenType.N_VAR:
            raise FizzLSPRenameError(
                "n", "",
                "Cannot rename the sacred variable 'n'. It is immutable in name as in purpose.",
            )

        if token.type in (
            TokenType.RULE, TokenType.WHEN, TokenType.EMIT,
            TokenType.EVALUATE, TokenType.TO, TokenType.LET,
            TokenType.PRIORITY, TokenType.AND, TokenType.OR,
            TokenType.NOT, TokenType.TRUE, TokenType.FALSE,
        ):
            raise FizzLSPRenameError(
                str(token.value), "",
                "Cannot rename a keyword. The language specification is not negotiable.",
            )

        if token.type != TokenType.IDENTIFIER:
            return None

        name = token.value
        info = symbol_table.get_symbol(name)

        if info and info.kind == "function":
            raise FizzLSPRenameError(
                name, "",
                f"Cannot rename stdlib function '{name}'. The standard library is a covenant, not a suggestion.",
            )

        tok_line = token.line - 1
        tok_col = token.col - 1
        return {
            "range": {
                "start": {"line": tok_line, "character": tok_col},
                "end": {"line": tok_line, "character": tok_col + len(name)},
            },
            "placeholder": name,
        }

    def rename(
        self,
        uri: str,
        position: LSPPosition,
        new_name: str,
        symbol_table: SymbolTable,
        ast: Any,
        tokens: List,
        source: str = "",
    ) -> WorkspaceEdit:
        """Compute all text edits for a rename operation."""
        token = DefinitionProvider()._find_token_at_position(tokens, position)
        if token is None:
            return WorkspaceEdit()

        old_name = token.value
        self._validate_identifier(new_name, old_name)
        self._check_conflicts(new_name, symbol_table, old_name)

        # Collect all reference locations
        refs_provider = ReferencesProvider()
        locs = refs_provider.references(
            uri, position, include_declaration=True,
            symbol_table=symbol_table, ast=ast, tokens=tokens, source=source,
        )

        edits: List[TextEdit] = []
        for loc in locs:
            edits.append(TextEdit(
                range=loc.range,
                new_text=new_name,
            ))

        return WorkspaceEdit(changes={uri: edits})

    def _validate_identifier(self, name: str, old_name: str) -> None:
        """Validate that a new name is a legal FizzLang identifier."""
        if not name:
            raise FizzLSPRenameError(old_name, name, "Name cannot be empty")
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
            raise FizzLSPRenameError(
                old_name, name,
                "Invalid identifier syntax. Must start with letter or underscore, "
                "followed by letters, digits, or underscores.",
            )
        if name.lower() in _FIZZLANG_KEYWORDS:
            raise FizzLSPRenameError(
                old_name, name,
                f"'{name}' is a reserved keyword.",
            )
        if name == "n":
            raise FizzLSPRenameError(
                old_name, name,
                "Cannot rename to 'n'. The sacred variable is reserved.",
            )

    def _check_conflicts(self, new_name: str, symbol_table: SymbolTable, old_name: str) -> None:
        """Check for naming conflicts."""
        existing = symbol_table.get_symbol(new_name)
        if existing and existing.name != old_name:
            loc = existing.definition_location
            loc_str = f"{loc.uri}:{loc.range.start.line}:{loc.range.start.character}"
            raise FizzLSPRenameConflictError(old_name, new_name, loc_str)


# ============================================================
# Workspace Symbol Provider
# ============================================================


class WorkspaceSymbolProvider:
    """Implements workspace/symbol.

    Searches all open documents' symbol tables for matching symbols.
    """

    def symbols(
        self,
        query: str,
        document_manager: TextDocumentManager,
        analysis_cache: Dict[str, AnalysisResult],
    ) -> List[Dict[str, Any]]:
        """Search for workspace symbols matching a query string."""
        results: List[Dict[str, Any]] = []
        query_lower = query.lower()

        for doc in document_manager.all_documents():
            analysis = analysis_cache.get(doc.uri)
            if analysis is None:
                continue

            for info in analysis.symbol_table.to_list():
                if query_lower and query_lower not in info.name.lower():
                    continue

                kind_map = {
                    "rule": SymbolKind.FUNCTION.value,
                    "variable": SymbolKind.VARIABLE.value,
                    "function": SymbolKind.METHOD.value,
                }

                # Extract filename from URI
                container = doc.uri.rsplit("/", 1)[-1] if "/" in doc.uri else doc.uri

                results.append({
                    "name": info.name,
                    "kind": kind_map.get(info.kind, SymbolKind.VARIABLE.value),
                    "location": {
                        "uri": info.definition_location.uri,
                        "range": {
                            "start": {
                                "line": info.definition_location.range.start.line,
                                "character": info.definition_location.range.start.character,
                            },
                            "end": {
                                "line": info.definition_location.range.end.line,
                                "character": info.definition_location.range.end.character,
                            },
                        },
                    },
                    "containerName": container,
                })

        return results


# ============================================================
# Semantic Token Provider
# ============================================================


class SemanticTokenProvider:
    """Implements textDocument/semanticTokens/full and range.

    Encodes classified tokens in the LSP delta-encoded format:
    five integers per token (delta line, delta start char, length,
    token type index, token modifier bitset).
    """

    def full(
        self, uri: str, semantic_tokens: List[Tuple[int, int, int, int, int]]
    ) -> Dict[str, Any]:
        """Return all semantic tokens in delta-encoded format."""
        data: List[int] = []
        for delta_line, delta_char, length, token_type, modifiers in semantic_tokens:
            data.extend([delta_line, delta_char, length, token_type, modifiers])
        return {"data": data}

    def range(
        self,
        uri: str,
        lsp_range: LSPRange,
        semantic_tokens: List[Tuple[int, int, int, int, int]],
    ) -> Dict[str, Any]:
        """Return semantic tokens filtered to the requested range."""
        # Reconstruct absolute positions from delta encoding
        filtered_data: List[Tuple[int, int, int, int, int]] = []
        abs_line = 0
        abs_char = 0
        for delta_line, delta_char, length, token_type, modifiers in semantic_tokens:
            if delta_line > 0:
                abs_line += delta_line
                abs_char = delta_char
            else:
                abs_char += delta_char

            if (lsp_range.start.line <= abs_line <= lsp_range.end.line):
                filtered_data.append((delta_line, delta_char, length, token_type, modifiers))

        # Re-encode filtered tokens
        result: List[int] = []
        prev_line = 0
        prev_char = 0
        first = True
        abs_line = 0
        abs_char = 0
        for delta_line, delta_char, length, token_type, modifiers in semantic_tokens:
            if delta_line > 0:
                abs_line += delta_line
                abs_char = delta_char
            else:
                abs_char += delta_char

            if lsp_range.start.line <= abs_line <= lsp_range.end.line:
                if first:
                    new_delta_line = abs_line - 0
                    new_delta_char = abs_char
                    first = False
                else:
                    new_delta_line = abs_line - prev_line
                    new_delta_char = abs_char - (prev_char if new_delta_line == 0 else 0)

                result.extend([new_delta_line, new_delta_char, length, token_type, modifiers])
                prev_line = abs_line
                prev_char = abs_char

        return {"data": result}

    @staticmethod
    def get_legend() -> Dict[str, Any]:
        """Return the token type and modifier legends."""
        return {
            "tokenTypes": [t.name.lower() for t in SemanticTokenType],
            "tokenModifiers": [m.name.lower() for m in SemanticTokenModifier],
        }


# ============================================================
# Code Action Provider
# ============================================================


class CodeActionProvider:
    """Implements textDocument/codeAction.

    Produces quick fixes for diagnostics, refactoring suggestions, and
    source-level actions.
    """

    def code_actions(
        self,
        uri: str,
        lsp_range: LSPRange,
        diagnostics: List[LSPDiagnostic],
        symbol_table: SymbolTable,
        ast: Any,
        source: str,
    ) -> List[Dict[str, Any]]:
        """Compute code actions for the given range and diagnostics."""
        actions: List[Dict[str, Any]] = []

        for diag in diagnostics:
            if "undefined" in diag.message.lower():
                fix = self._fix_similar_identifier(diag, symbol_table, uri)
                if fix:
                    actions.append(fix)
                fix = self._fix_add_let_binding(diag, source, uri)
                if fix:
                    actions.append(fix)

            if "duplicate" in diag.message.lower() and "rule" in diag.message.lower():
                fix = self._fix_duplicate_rule_name(diag, source, uri)
                if fix:
                    actions.append(fix)

            if "negative" in diag.message.lower() and "priority" in diag.message.lower():
                fix = self._fix_negative_priority(diag, source, uri)
                if fix:
                    actions.append(fix)

        # Refactoring: reorder rules by priority
        reorder = self._refactor_reorder_rules(ast, source, uri)
        if reorder:
            actions.append(reorder)

        return actions

    def _fix_similar_identifier(
        self, diag: LSPDiagnostic, symbol_table: SymbolTable, uri: str
    ) -> Optional[Dict[str, Any]]:
        """Suggest replacing a typo with a similar identifier."""
        m = re.search(r"'(\w+)'", diag.message)
        if not m:
            return None
        typo = m.group(1)
        similar = symbol_table.find_similar_name(typo)
        if not similar:
            return None
        return {
            "title": f"Replace '{typo}' with '{similar}'",
            "kind": CodeActionKind.QUICKFIX.value,
            "diagnostics": [{"code": diag.code, "message": diag.message}],
            "edit": {
                "changes": {
                    uri: [{
                        "range": {
                            "start": {"line": diag.range.start.line, "character": diag.range.start.character},
                            "end": {"line": diag.range.end.line, "character": diag.range.end.character},
                        },
                        "newText": similar,
                    }]
                }
            },
        }

    def _fix_add_let_binding(
        self, diag: LSPDiagnostic, source: str, uri: str
    ) -> Optional[Dict[str, Any]]:
        """Insert a let binding for an undefined variable."""
        m = re.search(r"'(\w+)'", diag.message)
        if not m:
            return None
        name = m.group(1)
        return {
            "title": f"Add 'let {name} = 0' before this line",
            "kind": CodeActionKind.QUICKFIX.value,
            "edit": {
                "changes": {
                    uri: [{
                        "range": {
                            "start": {"line": diag.range.start.line, "character": 0},
                            "end": {"line": diag.range.start.line, "character": 0},
                        },
                        "newText": f"let {name} = 0\n",
                    }]
                }
            },
        }

    def _fix_duplicate_rule_name(
        self, diag: LSPDiagnostic, source: str, uri: str
    ) -> Optional[Dict[str, Any]]:
        """Append a numeric suffix to a duplicate rule name."""
        m = re.search(r"'(\w+)'", diag.message)
        if not m:
            return None
        name = m.group(1)
        new_name = f"{name}_2"
        return {
            "title": f"Rename to '{new_name}'",
            "kind": CodeActionKind.QUICKFIX.value,
            "edit": {
                "changes": {
                    uri: [{
                        "range": {
                            "start": {"line": diag.range.start.line, "character": diag.range.start.character},
                            "end": {"line": diag.range.end.line, "character": diag.range.end.character},
                        },
                        "newText": new_name,
                    }]
                }
            },
        }

    def _fix_negative_priority(
        self, diag: LSPDiagnostic, source: str, uri: str
    ) -> Optional[Dict[str, Any]]:
        """Change negative priority to 0."""
        return {
            "title": "Change priority to 0",
            "kind": CodeActionKind.QUICKFIX.value,
            "edit": {
                "changes": {
                    uri: [{
                        "range": {
                            "start": {"line": diag.range.start.line, "character": diag.range.start.character},
                            "end": {"line": diag.range.end.line, "character": diag.range.end.character},
                        },
                        "newText": "0",
                    }]
                }
            },
        }

    def _refactor_reorder_rules(
        self, ast: Any, source: str, uri: str
    ) -> Optional[Dict[str, Any]]:
        """Offer to reorder rules by descending priority."""
        if ast is None:
            return None

        from enterprise_fizzbuzz.infrastructure.fizzlang import RuleNode

        rules = [(i, stmt) for i, stmt in enumerate(getattr(ast, "statements", []))
                 if isinstance(stmt, RuleNode)]

        if len(rules) < 2:
            return None

        priorities = [r.priority for _, r in rules]
        if priorities == sorted(priorities, reverse=True):
            return None  # Already in order

        return {
            "title": "Reorder rules by descending priority",
            "kind": CodeActionKind.REFACTOR_REWRITE.value,
        }


# ============================================================
# Document Formatting Provider
# ============================================================


class FormattingProvider:
    """Implements textDocument/formatting.

    Produces text edits transforming a FizzLang document to canonical style.
    """

    def format(
        self,
        uri: str,
        analysis: Optional[AnalysisResult],
        source: str,
    ) -> List[TextEdit]:
        """Format the document according to canonical FizzLang style."""
        formatted = self._reformat(source)
        if formatted == source:
            return []
        return self._compute_edits(source, formatted)

    def _reformat(self, source: str) -> str:
        """Re-emit source with canonical spacing and structure."""
        lines = source.split("\n")
        result_lines: List[str] = []
        prev_was_blank = True  # Start as if preceding line was blank

        for line in lines:
            stripped = line.rstrip()  # Remove trailing whitespace

            if not stripped:
                if not prev_was_blank and result_lines:
                    result_lines.append("")
                    prev_was_blank = True
                continue

            # Canonicalize keywords to lowercase
            words = stripped.split()
            if words:
                first = words[0].lower()
                if first in _FIZZLANG_KEYWORDS:
                    words[0] = first
                stripped = " ".join(words)

            # Normalize operator spacing
            stripped = re.sub(r'\s*(==|!=|<=|>=|<|>)\s*', r' \1 ', stripped)
            stripped = re.sub(r'\s*(%)\s*', r' \1 ', stripped)
            # Clean up multiple spaces
            stripped = re.sub(r'  +', ' ', stripped)

            # No space inside parens
            stripped = re.sub(r'\(\s+', '(', stripped)
            stripped = re.sub(r'\s+\)', ')', stripped)
            # No space before comma, one space after
            stripped = re.sub(r'\s*,\s*', ', ', stripped)

            result_lines.append(stripped)
            prev_was_blank = False

        # Remove leading blank lines
        while result_lines and not result_lines[0]:
            result_lines.pop(0)

        # Remove trailing blank lines, then add exactly one final newline
        while result_lines and not result_lines[-1]:
            result_lines.pop()

        return "\n".join(result_lines) + "\n" if result_lines else "\n"

    def _compute_edits(self, original: str, formatted: str) -> List[TextEdit]:
        """Compute a minimal edit to transform original into formatted."""
        orig_lines = original.split("\n")
        return [TextEdit(
            range=LSPRange(
                start=LSPPosition(line=0, character=0),
                end=LSPPosition(line=len(orig_lines) - 1, character=len(orig_lines[-1])),
            ),
            new_text=formatted,
        )]

    def _apply_edit(self, text: str, edit: TextEdit) -> str:
        """Apply a single text edit to a string."""
        lines = text.split("\n")
        start = edit.range.start
        end = edit.range.end
        before = "\n".join(lines[:start.line]) + ("\n" if start.line > 0 else "") + lines[start.line][:start.character]
        after = lines[end.line][end.character:] + ("\n" if end.line < len(lines) - 1 else "") + "\n".join(lines[end.line + 1:])
        return before + edit.new_text + after


# ============================================================
# Document Symbol Provider
# ============================================================


class DocumentSymbolProvider:
    """Implements textDocument/documentSymbol.

    Walks the AST to produce a hierarchical document outline.
    """

    def symbols(self, uri: str, ast: Any) -> List[DocumentSymbol]:
        """Produce a hierarchical symbol outline from the AST."""
        if ast is None:
            return []

        from enterprise_fizzbuzz.infrastructure.fizzlang import (
            EvaluateNode,
            LetNode,
            RuleNode,
        )

        result: List[DocumentSymbol] = []
        pipeline = AnalysisPipeline()

        for stmt in getattr(ast, "statements", []):
            line = getattr(stmt, "line", 1) - 1

            if isinstance(stmt, RuleNode):
                cond_str = pipeline._node_to_string(stmt.condition) if stmt.condition else ""
                emit_str = pipeline._node_to_string(stmt.emit_expr) if stmt.emit_expr else ""
                detail = f"when {cond_str} emit {emit_str}"

                children: List[DocumentSymbol] = []
                if stmt.condition:
                    children.append(DocumentSymbol(
                        name="condition",
                        detail=cond_str,
                        kind=SymbolKind.BOOLEAN,
                        range=LSPRange(start=LSPPosition(line=line, character=0), end=LSPPosition(line=line, character=0)),
                        selection_range=LSPRange(start=LSPPosition(line=line, character=0), end=LSPPosition(line=line, character=0)),
                    ))
                if stmt.emit_expr:
                    children.append(DocumentSymbol(
                        name="emit",
                        detail=emit_str,
                        kind=SymbolKind.STRING,
                        range=LSPRange(start=LSPPosition(line=line, character=0), end=LSPPosition(line=line, character=0)),
                        selection_range=LSPRange(start=LSPPosition(line=line, character=0), end=LSPPosition(line=line, character=0)),
                    ))
                children.append(DocumentSymbol(
                    name="priority",
                    detail=str(stmt.priority),
                    kind=SymbolKind.NUMBER,
                    range=LSPRange(start=LSPPosition(line=line, character=0), end=LSPPosition(line=line, character=0)),
                    selection_range=LSPRange(start=LSPPosition(line=line, character=0), end=LSPPosition(line=line, character=0)),
                ))

                result.append(DocumentSymbol(
                    name=stmt.name,
                    detail=detail,
                    kind=SymbolKind.FUNCTION,
                    range=LSPRange(start=LSPPosition(line=line, character=0), end=LSPPosition(line=line, character=80)),
                    selection_range=LSPRange(start=LSPPosition(line=line, character=5), end=LSPPosition(line=line, character=5 + len(stmt.name))),
                    children=children,
                ))

            elif isinstance(stmt, LetNode):
                val_str = pipeline._node_to_string(stmt.value) if stmt.value else ""
                result.append(DocumentSymbol(
                    name=stmt.name,
                    detail=val_str,
                    kind=SymbolKind.VARIABLE,
                    range=LSPRange(start=LSPPosition(line=line, character=0), end=LSPPosition(line=line, character=80)),
                    selection_range=LSPRange(start=LSPPosition(line=line, character=4), end=LSPPosition(line=line, character=4 + len(stmt.name))),
                ))

            elif isinstance(stmt, EvaluateNode):
                start_str = pipeline._node_to_string(stmt.start) if stmt.start else ""
                end_str = pipeline._node_to_string(stmt.end) if stmt.end else ""
                result.append(DocumentSymbol(
                    name="evaluate",
                    detail=f"{start_str} to {end_str}",
                    kind=SymbolKind.EVENT,
                    range=LSPRange(start=LSPPosition(line=line, character=0), end=LSPPosition(line=line, character=80)),
                    selection_range=LSPRange(start=LSPPosition(line=line, character=0), end=LSPPosition(line=line, character=8)),
                ))

        return result


# ============================================================
# FizzLSP Server
# ============================================================


class FizzLSPServer:
    """The top-level FizzLSP server wiring all providers together.

    Manages the full LSP lifecycle: initialization handshake, document
    synchronization, request dispatch, and shutdown.
    """

    def __init__(
        self,
        transport_type: str = DEFAULT_TRANSPORT,
        tcp_port: int = DEFAULT_TCP_PORT,
        debounce_ms: int = DEFAULT_DIAGNOSTIC_DEBOUNCE_MS,
        max_completion_items: int = DEFAULT_MAX_COMPLETION_ITEMS,
        semantic_tokens_enabled: bool = True,
        dependent_type_diagnostics: bool = True,
    ) -> None:
        self._state = LSPServerState.UNINITIALIZED
        self._transport_type = transport_type
        self._tcp_port = tcp_port
        self._capabilities = LSPServerCapabilities()

        # Create transport
        if transport_type == "tcp":
            self._transport: LSPTransport = TCPTransport(port=tcp_port)
        else:
            self._transport = StdioTransport()

        # Subsystems
        self._dispatcher = LSPDispatcher()
        self._doc_manager = TextDocumentManager()
        self._pipeline = AnalysisPipeline(
            dependent_type_diagnostics=dependent_type_diagnostics,
        )
        self._analysis_cache: Dict[str, AnalysisResult] = {}
        self._completion_provider = CompletionProvider(max_items=max_completion_items)
        self._diagnostic_publisher = DiagnosticPublisher()
        self._diagnostic_throttler = DiagnosticThrottler(debounce_ms=debounce_ms)
        self._definition_provider = DefinitionProvider()
        self._hover_provider = HoverProvider()
        self._references_provider = ReferencesProvider()
        self._rename_provider = RenameProvider()
        self._workspace_symbol_provider = WorkspaceSymbolProvider()
        self._semantic_token_provider = SemanticTokenProvider()
        self._code_action_provider = CodeActionProvider()
        self._formatting_provider = FormattingProvider()
        self._document_symbol_provider = DocumentSymbolProvider()
        self._metrics = FizzLSPMetrics()
        self._client_capabilities: Dict[str, Any] = {}
        self._semantic_tokens_enabled = semantic_tokens_enabled
        self._notifications: List[LSPMessage] = []

        # Register handlers
        self._register_handlers()

    @property
    def state(self) -> LSPServerState:
        return self._state

    def handle_message(self, raw: str) -> Optional[str]:
        """Decode an incoming message, dispatch, and return the encoded response."""
        try:
            message = LSPMessage.decode(raw)
        except FizzLSPTransportError as e:
            error_response = LSPMessage(
                id=None,
                error={"code": JSONRPC_PARSE_ERROR, "message": str(e)},
            )
            return error_response.encode()

        self._dispatcher._log_message("IN", message)
        self._metrics.requests_processed += 1

        start = time.monotonic()
        response = self._dispatcher.dispatch(message)
        elapsed = (time.monotonic() - start) * 1000

        method = message.method or "unknown"
        self._metrics.avg_response_time_ms[method] = elapsed

        # Collect any pending notifications
        self._diagnostic_throttler.flush_all()
        notifications = list(self._notifications)
        self._notifications.clear()

        result_parts = []
        if response is not None:
            self._dispatcher._log_message("OUT", response)
            result_parts.append(response.encode())
        for notif in notifications:
            result_parts.append(notif.encode())

        return "\n".join(result_parts) if result_parts else None

    def simulate_session(self, messages: Optional[List[str]] = None) -> List[str]:
        """Process a sequence of raw LSP messages and return responses.

        If no messages are provided, runs a predefined editor simulation.
        """
        if messages is None:
            messages = self._predefined_session()

        responses: List[str] = []
        for raw in messages:
            result = self.handle_message(raw)
            if result:
                responses.append(result)
        return responses

    def _predefined_session(self) -> List[str]:
        """Generate a predefined editor simulation session."""
        sample = 'let divisor = 3\nrule fizz when n % divisor == 0 emit "Fizz" priority 1\nrule buzz when n % 5 == 0 emit "Buzz" priority 1\nevaluate 1 to 20\n'
        uri = "file:///workspace/demo.fizzlang"

        def _msg(method: str, params: Dict, msg_id: Optional[int] = None) -> str:
            m = LSPMessage(id=msg_id, method=method, params=params)
            return m.encode()

        return [
            _msg("initialize", {"capabilities": {}}, msg_id=1),
            _msg("initialized", {}),
            _msg("textDocument/didOpen", {
                "textDocument": {
                    "uri": uri,
                    "languageId": "fizzlang",
                    "version": 1,
                    "text": sample,
                },
            }),
            _msg("textDocument/completion", {
                "textDocument": {"uri": uri},
                "position": {"line": 0, "character": 0},
            }, msg_id=2),
            _msg("textDocument/hover", {
                "textDocument": {"uri": uri},
                "position": {"line": 1, "character": 20},
            }, msg_id=3),
            _msg("shutdown", {}, msg_id=4),
            _msg("exit", {}),
        ]

    def _initialize_handshake(self) -> None:
        """Perform the initialize/initialized handshake internally."""
        self._handle_initialize({"capabilities": {}})
        self._handle_initialized({})

    def _register_handlers(self) -> None:
        """Register all LSP method handlers with the dispatcher."""
        self._dispatcher.register("initialize", self._handle_initialize)
        self._dispatcher.register("initialized", self._handle_initialized)
        self._dispatcher.register("shutdown", self._handle_shutdown)
        self._dispatcher.register("exit", self._handle_exit)
        self._dispatcher.register("textDocument/didOpen", self._handle_did_open)
        self._dispatcher.register("textDocument/didChange", self._handle_did_change)
        self._dispatcher.register("textDocument/didClose", self._handle_did_close)
        self._dispatcher.register("textDocument/completion", self._handle_completion)
        self._dispatcher.register("completionItem/resolve", self._handle_completion_resolve)
        self._dispatcher.register("textDocument/hover", self._handle_hover)
        self._dispatcher.register("textDocument/definition", self._handle_definition)
        self._dispatcher.register("textDocument/references", self._handle_references)
        self._dispatcher.register("textDocument/rename", self._handle_rename)
        self._dispatcher.register("textDocument/prepareRename", self._handle_prepare_rename)
        self._dispatcher.register("workspace/symbol", self._handle_workspace_symbol)
        self._dispatcher.register("textDocument/semanticTokens/full", self._handle_semantic_tokens_full)
        self._dispatcher.register("textDocument/semanticTokens/range", self._handle_semantic_tokens_range)
        self._dispatcher.register("textDocument/codeAction", self._handle_code_action)
        self._dispatcher.register("textDocument/formatting", self._handle_formatting)
        self._dispatcher.register("textDocument/documentSymbol", self._handle_document_symbol)

    # ----------------------------------------------------------
    # Lifecycle Handlers
    # ----------------------------------------------------------

    def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Process the initialize request."""
        if self._state != LSPServerState.UNINITIALIZED:
            raise FizzLSPSessionError("Server already initialized")
        _validate_transition(self._state, LSPServerState.INITIALIZING)
        self._state = LSPServerState.INITIALIZING
        self._client_capabilities = params.get("capabilities", {})
        return {
            "capabilities": self._capabilities.to_dict(),
            "serverInfo": {
                "name": FIZZLSP_SERVER_NAME,
                "version": FIZZLSP_VERSION,
            },
        }

    def _handle_initialized(self, params: Dict[str, Any]) -> None:
        """Process the initialized notification."""
        _validate_transition(self._state, LSPServerState.RUNNING)
        self._state = LSPServerState.RUNNING
        logger.info("FizzLSP server initialized and running")

    def _handle_shutdown(self, params: Dict[str, Any]) -> None:
        """Process the shutdown request."""
        _validate_transition(self._state, LSPServerState.SHUTTING_DOWN)
        self._state = LSPServerState.SHUTTING_DOWN
        return None

    def _handle_exit(self, params: Dict[str, Any]) -> None:
        """Process the exit notification."""
        exit_code = 0 if self._state == LSPServerState.SHUTTING_DOWN else 1
        self._state = LSPServerState.TERMINATED
        return None

    # ----------------------------------------------------------
    # Document Sync Handlers
    # ----------------------------------------------------------

    def _handle_did_open(self, params: Dict[str, Any]) -> None:
        """Handle textDocument/didOpen."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        language_id = td.get("languageId", "fizzlang")
        version = td.get("version", 1)
        text = td.get("text", "")
        self._doc_manager.open_document(uri, language_id, version, text)
        self._on_document_change(uri)

    def _handle_did_change(self, params: Dict[str, Any]) -> None:
        """Handle textDocument/didChange."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        version = td.get("version", 0)
        changes = params.get("contentChanges", [])
        self._doc_manager.update_document(uri, changes, version)
        self._on_document_change(uri)

    def _handle_did_close(self, params: Dict[str, Any]) -> None:
        """Handle textDocument/didClose."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        self._doc_manager.close_document(uri)
        self._analysis_cache.pop(uri, None)
        notif = self._diagnostic_publisher.clear(uri)
        self._notifications.append(notif)

    # ----------------------------------------------------------
    # Feature Handlers
    # ----------------------------------------------------------

    def _handle_completion(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle textDocument/completion."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        pos = params.get("position", {})
        position = LSPPosition(line=pos.get("line", 0), character=pos.get("character", 0))
        context = params.get("context", {})
        analysis = self._analysis_cache.get(uri)
        doc = self._doc_manager.get_document(uri)
        source = doc.text if doc else ""
        items = self._completion_provider.complete(uri, position, context, analysis, source)
        self._metrics.completions_served += 1
        return {"isIncomplete": False, "items": [i.to_dict() for i in items]}

    def _handle_completion_resolve(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle completionItem/resolve."""
        return self._completion_provider.resolve(params)

    def _handle_hover(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle textDocument/hover."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        pos = params.get("position", {})
        position = LSPPosition(line=pos.get("line", 0), character=pos.get("character", 0))
        analysis = self._analysis_cache.get(uri)
        if not analysis:
            return None
        result = self._hover_provider.hover(
            uri, position, analysis.symbol_table, analysis.ast, analysis.tokens,
        )
        self._metrics.hovers_served += 1
        return result

    def _handle_definition(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle textDocument/definition."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        pos = params.get("position", {})
        position = LSPPosition(line=pos.get("line", 0), character=pos.get("character", 0))
        analysis = self._analysis_cache.get(uri)
        if not analysis:
            return None
        loc = self._definition_provider.definition(
            uri, position, analysis.symbol_table, analysis.ast, analysis.tokens,
        )
        self._metrics.definitions_resolved += 1
        if loc is None:
            return None
        return {
            "uri": loc.uri,
            "range": {
                "start": {"line": loc.range.start.line, "character": loc.range.start.character},
                "end": {"line": loc.range.end.line, "character": loc.range.end.character},
            },
        }

    def _handle_references(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle textDocument/references."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        pos = params.get("position", {})
        position = LSPPosition(line=pos.get("line", 0), character=pos.get("character", 0))
        context = params.get("context", {})
        include_declaration = context.get("includeDeclaration", True)
        analysis = self._analysis_cache.get(uri)
        if not analysis:
            return []
        doc = self._doc_manager.get_document(uri)
        source = doc.text if doc else ""
        locs = self._references_provider.references(
            uri, position, include_declaration,
            analysis.symbol_table, analysis.ast, analysis.tokens, source,
        )
        return [
            {
                "uri": loc.uri,
                "range": {
                    "start": {"line": loc.range.start.line, "character": loc.range.start.character},
                    "end": {"line": loc.range.end.line, "character": loc.range.end.character},
                },
            }
            for loc in locs
        ]

    def _handle_rename(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle textDocument/rename."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        pos = params.get("position", {})
        position = LSPPosition(line=pos.get("line", 0), character=pos.get("character", 0))
        new_name = params.get("newName", "")
        analysis = self._analysis_cache.get(uri)
        if not analysis:
            return {"changes": {}}
        doc = self._doc_manager.get_document(uri)
        source = doc.text if doc else ""
        edit = self._rename_provider.rename(
            uri, position, new_name,
            analysis.symbol_table, analysis.ast, analysis.tokens, source,
        )
        self._metrics.renames_performed += 1
        return edit.to_dict()

    def _handle_prepare_rename(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle textDocument/prepareRename."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        pos = params.get("position", {})
        position = LSPPosition(line=pos.get("line", 0), character=pos.get("character", 0))
        analysis = self._analysis_cache.get(uri)
        if not analysis:
            return None
        return self._rename_provider.prepare_rename(
            uri, position, analysis.symbol_table, analysis.tokens,
        )

    def _handle_workspace_symbol(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle workspace/symbol."""
        query = params.get("query", "")
        return self._workspace_symbol_provider.symbols(
            query, self._doc_manager, self._analysis_cache,
        )

    def _handle_semantic_tokens_full(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle textDocument/semanticTokens/full."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        analysis = self._analysis_cache.get(uri)
        if not analysis:
            return {"data": []}
        return self._semantic_token_provider.full(uri, analysis.semantic_tokens)

    def _handle_semantic_tokens_range(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle textDocument/semanticTokens/range."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        r = params.get("range", {})
        lsp_range = LSPRange(
            start=LSPPosition(
                line=r.get("start", {}).get("line", 0),
                character=r.get("start", {}).get("character", 0),
            ),
            end=LSPPosition(
                line=r.get("end", {}).get("line", 0),
                character=r.get("end", {}).get("character", 0),
            ),
        )
        analysis = self._analysis_cache.get(uri)
        if not analysis:
            return {"data": []}
        return self._semantic_token_provider.range(uri, lsp_range, analysis.semantic_tokens)

    def _handle_code_action(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle textDocument/codeAction."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        r = params.get("range", {})
        lsp_range = LSPRange(
            start=LSPPosition(
                line=r.get("start", {}).get("line", 0),
                character=r.get("start", {}).get("character", 0),
            ),
            end=LSPPosition(
                line=r.get("end", {}).get("line", 0),
                character=r.get("end", {}).get("character", 0),
            ),
        )
        context_diags = params.get("context", {}).get("diagnostics", [])
        analysis = self._analysis_cache.get(uri)
        if not analysis:
            return []
        doc = self._doc_manager.get_document(uri)
        source = doc.text if doc else ""

        # Convert context diagnostics to LSPDiagnostic objects
        diags = []
        for d in context_diags:
            dr = d.get("range", {})
            diags.append(LSPDiagnostic(
                range=LSPRange(
                    start=LSPPosition(
                        line=dr.get("start", {}).get("line", 0),
                        character=dr.get("start", {}).get("character", 0),
                    ),
                    end=LSPPosition(
                        line=dr.get("end", {}).get("line", 0),
                        character=dr.get("end", {}).get("character", 0),
                    ),
                ),
                severity=DiagnosticSeverity(d.get("severity", 1)),
                code=d.get("code", ""),
                message=d.get("message", ""),
            ))

        return self._code_action_provider.code_actions(
            uri, lsp_range, diags, analysis.symbol_table, analysis.ast, source,
        )

    def _handle_formatting(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle textDocument/formatting."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        analysis = self._analysis_cache.get(uri)
        doc = self._doc_manager.get_document(uri)
        source = doc.text if doc else ""
        edits = self._formatting_provider.format(uri, analysis, source)
        self._metrics.formatting_applied += 1
        return [e.to_dict() for e in edits]

    def _handle_document_symbol(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle textDocument/documentSymbol."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        analysis = self._analysis_cache.get(uri)
        if not analysis or not analysis.ast:
            return []
        symbols = self._document_symbol_provider.symbols(uri, analysis.ast)
        return [s.to_dict() for s in symbols]

    # ----------------------------------------------------------
    # Internal
    # ----------------------------------------------------------

    def _on_document_change(self, uri: str) -> None:
        """Run the analysis pipeline and schedule diagnostic publication."""
        doc = self._doc_manager.get_document(uri)
        if doc is None:
            return

        analysis = self._pipeline.analyze(uri, doc.text)
        self._analysis_cache[uri] = analysis

        def _publish() -> None:
            notif = self._diagnostic_publisher.publish(uri, analysis.diagnostics)
            self._notifications.append(notif)
            self._metrics.diagnostics_published += 1

        self._diagnostic_throttler.schedule(uri, _publish)


# ============================================================
# FizzLSP Dashboard
# ============================================================


class FizzLSPDashboard:
    """ASCII dashboard with box-drawing characters displaying server state.

    Renders server status, document inventory, diagnostic breakdown,
    protocol statistics, and the LSP Complexity Index.
    """

    @staticmethod
    def render(
        server: FizzLSPServer,
        width: int = DEFAULT_DASHBOARD_WIDTH,
        show_documents: bool = True,
        show_diagnostics: bool = True,
        show_protocol_stats: bool = True,
        show_complexity_index: bool = True,
    ) -> str:
        """Render the full FizzLSP dashboard."""
        lines: List[str] = []

        def _hline(ch: str = "─") -> str:
            return "┌" + ch * (width - 2) + "┐"

        def _mline(ch: str = "─") -> str:
            return "├" + ch * (width - 2) + "┤"

        def _bline(ch: str = "─") -> str:
            return "└" + ch * (width - 2) + "┘"

        def _row(text: str) -> str:
            return "│ " + text.ljust(width - 4) + " │"

        # Header
        lines.append(_hline())
        title = "FizzLSP Language Server Dashboard"
        lines.append(_row(title.center(width - 4)))
        lines.append(_mline())

        # Server state
        uptime = time.monotonic() - server._metrics.start_time
        lines.append(_row(f"Server State: {server._state.name}"))
        lines.append(_row(f"Uptime: {uptime:.1f}s"))
        lines.append(_row(f"Transport: {server._transport_type}"))
        lines.append(_row(f"Version: {FIZZLSP_VERSION}"))

        # Documents
        if show_documents:
            lines.append(_mline())
            lines.append(_row("Active Documents"))
            lines.append(_mline())
            docs = server._doc_manager.all_documents()
            if docs:
                for doc in docs:
                    analysis = server._analysis_cache.get(doc.uri)
                    sym_count = len(analysis.symbol_table.symbols) if analysis else 0
                    diag_count = len(analysis.diagnostics) if analysis else 0
                    name = doc.uri.rsplit("/", 1)[-1] if "/" in doc.uri else doc.uri
                    lines.append(_row(f"  {name} v{doc.version}  syms={sym_count} diags={diag_count}"))
            else:
                lines.append(_row("  (no documents open)"))

        # Diagnostics
        if show_diagnostics:
            lines.append(_mline())
            lines.append(_row("Diagnostic Breakdown"))
            lines.append(_mline())
            total_diags: Dict[str, int] = {"ERROR": 0, "WARNING": 0, "INFORMATION": 0, "HINT": 0}
            for analysis in server._analysis_cache.values():
                for d in analysis.diagnostics:
                    total_diags[d.severity.name] = total_diags.get(d.severity.name, 0) + 1
            for sev, count in total_diags.items():
                lines.append(_row(f"  {sev}: {count}"))

        # Protocol stats
        if show_protocol_stats:
            lines.append(_mline())
            lines.append(_row("Protocol Statistics"))
            lines.append(_mline())
            m = server._metrics
            lines.append(_row(f"  Requests processed: {m.requests_processed}"))
            lines.append(_row(f"  Completions served: {m.completions_served}"))
            lines.append(_row(f"  Definitions resolved: {m.definitions_resolved}"))
            lines.append(_row(f"  Hovers served: {m.hovers_served}"))
            lines.append(_row(f"  Renames performed: {m.renames_performed}"))
            lines.append(_row(f"  Diagnostics published: {m.diagnostics_published}"))

        # Complexity Index
        if show_complexity_index:
            lines.append(_mline())
            import os
            fizzlsp_path = os.path.join(
                os.path.dirname(__file__), "fizzlsp.py"
            )
            try:
                with open(fizzlsp_path, "r", encoding="utf-8") as f:
                    lsp_lines = sum(1 for _ in f)
            except (OSError, UnicodeDecodeError):
                lsp_lines = 3500  # Estimate
            core_lines = 10  # Core FizzBuzz: n%3==0, n%5==0, etc.
            ratio = lsp_lines / max(core_lines, 1)
            lines.append(_row(f"LSP Complexity Index"))
            lines.append(_row(f"  fizzlsp.py: {lsp_lines} lines"))
            lines.append(_row(f"  Core FizzBuzz: ~{core_lines} lines"))
            lines.append(_row(f"  Ratio: {ratio:.0f}:1"))

        lines.append(_bline())
        return "\n".join(lines)


# ============================================================
# Middleware Integration
# ============================================================


class FizzLSPMiddleware(IMiddleware):
    """Records language server activity during FizzBuzz evaluation.

    Captures server state, document count, diagnostic totals, and
    analysis pipeline latency into the processing context metadata.
    """

    def __init__(self, server: Optional[FizzLSPServer] = None) -> None:
        self._server = server

    def get_name(self) -> str:
        return "FizzLSPMiddleware"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Add FizzLSP metadata to the processing context."""
        if self._server is None:
            context.metadata["fizzlsp_state"] = "disabled"
            return next_handler(context)

        try:
            server = self._server
            context.metadata["fizzlsp_state"] = server._state.name
            context.metadata["fizzlsp_open_documents"] = server._doc_manager.document_count()

            total_diags = sum(
                len(a.diagnostics) for a in server._analysis_cache.values()
            )
            context.metadata["fizzlsp_total_diagnostics"] = total_diags

            avg_analysis = 0.0
            if server._analysis_cache:
                avg_analysis = sum(
                    a.analysis_time_ms for a in server._analysis_cache.values()
                ) / len(server._analysis_cache)
            context.metadata["fizzlsp_avg_analysis_ms"] = round(avg_analysis, 2)

        except Exception as e:
            raise FizzLSPMiddlewareError(f"Failed to record FizzLSP state: {e}")

        return next_handler(context)

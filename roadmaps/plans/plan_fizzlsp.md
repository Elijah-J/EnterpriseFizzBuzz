# Plan: FizzLSP -- Language Server Protocol for FizzLang

**Module**: `enterprise_fizzbuzz/infrastructure/fizzlsp.py`
**Target Size**: ~3,500 lines
**Test File**: `tests/test_fizzlsp.py` (~500 lines, ~100 tests)
**Re-export Stub**: `fizzlsp.py` (root)
**Middleware Priority**: 92

---

## 1. Module Docstring

```python
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
```

---

## 2. Imports

```python
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
```

---

## 3. Constants (~20 constants)

```python
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
```

---

## 4. Enums

### LSPServerState
```python
class LSPServerState(Enum):
    """Server lifecycle state machine.

    UNINITIALIZED -> INITIALIZING -> RUNNING -> SHUTTING_DOWN -> TERMINATED.
    Invalid transitions raise LSPProtocolError.  This mirrors FizzDAP's
    SessionState pattern but with LSP-specific states.
    """
    UNINITIALIZED = auto()
    INITIALIZING = auto()
    RUNNING = auto()
    SHUTTING_DOWN = auto()
    TERMINATED = auto()
```

### LSPMessageType
```python
class LSPMessageType(Enum):
    """JSON-RPC 2.0 message classification."""
    REQUEST = auto()       # Has id and method
    RESPONSE = auto()      # Has id and result/error
    NOTIFICATION = auto()  # Has method but no id
```

### TextDocumentSyncKind
```python
class TextDocumentSyncKind(Enum):
    """How the client sends document changes to the server."""
    NONE = 0
    FULL = 1
    INCREMENTAL = 2
```

### DiagnosticSeverity
```python
class DiagnosticSeverity(Enum):
    """LSP diagnostic severity levels."""
    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4
```

### DiagnosticTag
```python
class DiagnosticTag(Enum):
    """LSP diagnostic tags."""
    UNNECESSARY = 1
    DEPRECATED = 2
```

### CompletionItemKind
```python
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
```

### InsertTextFormat
```python
class InsertTextFormat(Enum):
    """Insert text format for completion items."""
    PLAIN_TEXT = 1
    SNIPPET = 2
```

### SymbolKind
```python
class SymbolKind(Enum):
    """LSP symbol kinds used by FizzLSP."""
    FUNCTION = 12    # Rules
    VARIABLE = 13    # Let-bindings
    BOOLEAN = 17     # Rule conditions
    STRING = 15      # Emit expressions
    NUMBER = 16      # Priority values
    EVENT = 24       # Evaluate statements
    METHOD = 6       # Stdlib functions
```

### CodeActionKind
```python
class CodeActionKind(Enum):
    """LSP code action kinds supported by FizzLSP."""
    QUICKFIX = "quickfix"
    REFACTOR_EXTRACT = "refactor.extract"
    REFACTOR_REWRITE = "refactor.rewrite"
    SOURCE_FIXALL = "source.fixAll"
```

### SemanticTokenType
```python
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
```

### SemanticTokenModifier
```python
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
```

---

## 5. Data Classes (~20 dataclasses)

### LSPPosition
```python
@dataclass
class LSPPosition:
    """Zero-indexed line and character position in a text document."""
    line: int
    character: int
```

### LSPRange
```python
@dataclass
class LSPRange:
    """A range in a text document, defined by start and end positions."""
    start: LSPPosition
    end: LSPPosition
```

### LSPLocation
```python
@dataclass
class LSPLocation:
    """A location in a document, identified by URI and range."""
    uri: str
    range: LSPRange
```

### LSPMessage
```python
@dataclass
class LSPMessage:
    """JSON-RPC 2.0 message with Content-Length header framing.

    Follows the identical wire format as DAPMessage:
    Content-Length: N\r\n\r\n{json_body}

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

    # ~30 lines: message_type property, encode() method producing
    # Content-Length header + \r\n\r\n + JSON body, decode() classmethod
    # parsing from wire format, from_dict() factory, to_dict() serialization,
    # is_request/is_response/is_notification properties.
```

### TextDocumentItem
```python
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
```

### LSPDiagnostic
```python
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
```

### SymbolInfo
```python
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
```

### SymbolTable
```python
@dataclass
class SymbolTable:
    """Maps symbol names to SymbolInfo records.

    Rebuilt on every document change because FizzLang's scoping rules are
    simple (all let-bindings are top-level) and the rebuild is sub-millisecond.
    """
    symbols: Dict[str, SymbolInfo] = field(default_factory=dict)
    # ~40 lines: add_symbol(), get_symbol(), find_at_position(),
    # find_references(), find_similar_name() (Levenshtein), all_rules(),
    # all_variables(), all_functions(), to_list() methods.
```

### AnalysisResult
```python
@dataclass
class AnalysisResult:
    """The product of the analysis pipeline for a single document."""
    diagnostics: List[LSPDiagnostic] = field(default_factory=list)
    ast: Any = None                      # ProgramNode or None
    tokens: List[Any] = field(default_factory=list)
    symbol_table: SymbolTable = field(default_factory=SymbolTable)
    semantic_tokens: List[Tuple[int, int, int, int, int]] = field(default_factory=list)
    analysis_time_ms: float = 0.0
```

### CompletionItem
```python
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
```

### TextEdit
```python
@dataclass
class TextEdit:
    """A text edit applied to a document."""
    range: LSPRange
    new_text: str
```

### WorkspaceEdit
```python
@dataclass
class WorkspaceEdit:
    """A set of text edits across documents."""
    changes: Dict[str, List[TextEdit]] = field(default_factory=dict)
```

### DocumentSymbol
```python
@dataclass
class DocumentSymbol:
    """A symbol in the document outline."""
    name: str
    detail: str
    kind: SymbolKind
    range: LSPRange
    selection_range: LSPRange
    children: List[DocumentSymbol] = field(default_factory=list)
```

### SemanticTokenData
```python
@dataclass
class SemanticTokenData:
    """Raw semantic token before delta encoding."""
    line: int
    start_char: int
    length: int
    token_type: SemanticTokenType
    modifiers: int = 0  # Bitset of SemanticTokenModifier values
```

### LSPServerCapabilities
```python
@dataclass
class LSPServerCapabilities:
    """The full set of capabilities the FizzLSP server supports.

    Declared during the initialize handshake.  Each capability maps to
    a provider class that implements the corresponding LSP method.
    """
    # ~30 lines: all capability fields with their values as described
    # in the brainstorm (textDocumentSync, completionProvider, hoverProvider,
    # definitionProvider, referencesProvider, renameProvider,
    # documentSymbolProvider, workspaceSymbolProvider, semanticTokensProvider,
    # codeActionProvider, documentFormattingProvider, diagnosticProvider).
    # to_dict() method serializing to LSP InitializeResult format.
```

### FizzLSPMetrics
```python
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
    start_time: float = field(default_factory=time.monotonic)
```

---

## 6. JSON-RPC Transport Layer (~250 lines)

### LSPMessage (full implementation)
~60 lines. Encode/decode methods producing `Content-Length: N\r\n\r\n{json}` wire format. The `encode()` method serializes the message dict to JSON, encodes to UTF-8, computes the byte length, and prepends the Content-Length header. The `decode()` classmethod parses the Content-Length header, reads the body, and constructs the message. Raises `FizzLSPTransportError` on malformed input (missing header, non-integer content length, truncated body, invalid JSON).

### LSPTransport (abstract base)
~15 lines. Abstract base class defining `send(message: LSPMessage)` and `receive() -> LSPMessage`.

### StdioTransport
~40 lines. Reads from and writes to in-memory `StringIO` buffers. Constructor accepts `input_buffer: StringIO` and `output_buffer: StringIO`. The `send()` method encodes the message and writes to the output buffer. The `receive()` method reads from the input buffer, parsing Content-Length headers and extracting JSON bodies. Handles the edge case where the input buffer is exhausted (returns None, indicating end of stream).

### TCPTransport
~40 lines. Simulated TCP transport using in-memory byte buffer pairs (`client_to_server: bytearray`, `server_to_client: bytearray`). Same Content-Length framing over the simulated socket stream. Constructor accepts optional host and port for logging purposes.

### LSPDispatcher
~90 lines. Routes incoming JSON-RPC messages to registered handler callables.

- `_handlers: Dict[str, Callable]` -- maps method names to handler functions.
- `register(method: str, handler: Callable)` -- registers a handler.
- `dispatch(message: LSPMessage) -> Optional[LSPMessage]` -- looks up the handler for `message.method`, invokes it with `message.params`, and wraps the return value in a response message. For notifications (no `id`), the handler is called but no response is generated. For unknown methods, returns a `MethodNotFound` error response (code -32601). Catches exceptions from handlers and wraps them in JSON-RPC internal error responses.
- `_log_message(direction: str, message: LSPMessage)` -- logs all incoming and outgoing messages for protocol debugging.
- Raises `FizzLSPDispatchError` for handler registration conflicts (duplicate method names).

---

## 7. Initialization Handshake (~200 lines)

### LSPServerState (state machine)
~40 lines. Enum plus transition validation.

- `VALID_TRANSITIONS: Dict[LSPServerState, Set[LSPServerState]]` -- class-level mapping defining legal transitions.
- `validate_transition(current: LSPServerState, target: LSPServerState)` -- raises `FizzLSPProtocolError` if the transition is not in `VALID_TRANSITIONS`.
- Valid transitions:
  - UNINITIALIZED -> INITIALIZING
  - INITIALIZING -> RUNNING
  - RUNNING -> SHUTTING_DOWN
  - SHUTTING_DOWN -> TERMINATED
  - Any state -> TERMINATED (for abnormal exit)

### LSPServerCapabilities (full to_dict)
~50 lines. Constructs the complete capabilities dictionary as specified in the brainstorm:
- `textDocumentSync: TextDocumentSyncKind.INCREMENTAL` (2)
- `completionProvider: { triggerCharacters: [".", "%", "(", " "], resolveProvider: true }`
- `hoverProvider: true`
- `definitionProvider: true`
- `referencesProvider: true`
- `renameProvider: { prepareProvider: true }`
- `documentSymbolProvider: true`
- `workspaceSymbolProvider: true`
- `semanticTokensProvider: { full: true, range: true, legend: { tokenTypes: [...12...], tokenModifiers: [...8...] } }`
- `codeActionProvider: { codeActionKinds: ["quickfix", "refactor.extract", "refactor.rewrite", "source.fixAll"] }`
- `documentFormattingProvider: true`
- `diagnosticProvider: { interFileDiagnostics: false, workspaceDiagnostics: false }`

### InitializeHandler
~40 lines. Processes the `initialize` request.
- Reads client capabilities from params.
- Stores client capabilities for conditional feature activation (e.g., workspace/configuration support, window/workDoneProgress support, publishDiagnostics with relatedInformation).
- Returns `InitializeResult` containing server capabilities and server info `{ name: "FizzLSP", version: "1.0.0" }`.
- Transitions server state UNINITIALIZED -> INITIALIZING.
- Raises `FizzLSPSessionError` if called when not UNINITIALIZED.

### InitializedHandler
~15 lines. Processes the `initialized` notification.
- Transitions state INITIALIZING -> RUNNING.
- Logs activation. No return value (notification).

### ShutdownHandler
~15 lines. Processes the `shutdown` request.
- Transitions state to SHUTTING_DOWN.
- Returns null result.

### ExitHandler
~15 lines. Processes the `exit` notification.
- Transitions state to TERMINATED.
- Returns exit code 0 if shutdown was received first, 1 otherwise.

---

## 8. Document Synchronization (~200 lines)

### TextDocumentManager
~100 lines. Manages the set of open documents.

- `_documents: Dict[str, TextDocumentItem]` -- maps URI to document.
- `open_document(uri, language_id, version, text)` -- creates new `TextDocumentItem`, stores it, returns the document. Raises `FizzLSPDocumentError` if already open.
- `update_document(uri, changes, version)` -- applies incremental changes via `IncrementalSyncEngine`, bumps version. Raises `FizzLSPDocumentSyncError` if document not open or version is out-of-order.
- `close_document(uri)` -- removes document. Raises `FizzLSPDocumentError` if not open.
- `get_document(uri) -> Optional[TextDocumentItem]` -- retrieves by URI.
- `all_documents() -> List[TextDocumentItem]` -- returns all open documents.
- `document_count() -> int`.

### IncrementalSyncEngine
~100 lines. Applies text edits to a document buffer.

- `apply_changes(text: str, changes: List[Dict]) -> str` -- applies each change in order. Each change has a `range` (start line/character to end line/character) and `text` to replace that range with.
- `_position_to_offset(text: str, line: int, character: int) -> int` -- converts line/character to byte offset by computing line start offsets.
- `_offset_to_position(text: str, offset: int) -> LSPPosition` -- converts byte offset back to line/character.
- `_compute_line_starts(text: str) -> List[int]` -- precomputes line start offsets.
- Handles edge cases: insertions at document end, deletions spanning multiple lines, replacements that change line count. Validates ranges are within document bounds, raises `FizzLSPDocumentSyncError` for out-of-bounds ranges.

---

## 9. Analysis Pipeline (~300 lines)

### AnalysisPipeline
~200 lines. Orchestrates four analysis passes on each document change.

- `analyze(uri: str, source: str) -> AnalysisResult` -- runs the full pipeline:
  1. **Lexical analysis**: imports and calls `fizzlang.Lexer(source).tokenize()`. Catches `FizzLangLexerError`, converts to `LSPDiagnostic` with severity ERROR and code "EFP-FL11". Continues with partial token stream.
  2. **Syntactic analysis**: imports and calls `fizzlang.Parser(tokens).parse()`. Catches `FizzLangParseError`, converts to diagnostic with code "EFP-FL12". Attempts up to `MAX_PARSE_RECOVERY_ATTEMPTS` recovery passes by inserting synthetic tokens at the error location. Produces partial AST even with errors.
  3. **Semantic analysis**: imports and calls `fizzlang.TypeChecker().check(ast)` on the (possibly partial) AST. `FizzLangTypeError` -> ERROR diagnostic with code "EFP-FL13". Warnings -> WARNING diagnostics.
  4. **Dependent type analysis**: imports `dependent_types` module, runs lightweight proof obligation check on `evaluate` statements. `TypeCheckError` and `ProofObligationError` -> INFORMATION diagnostics (proof-theoretic observations, not programming errors).
  5. **Symbol collection**: calls `_collect_symbols(ast, tokens, uri)`.
  6. **Semantic token classification**: calls `_classify_tokens(tokens, ast)`.
- `_collect_symbols(ast, tokens, uri) -> SymbolTable` -- walks AST, collects rule names (kind="rule"), let-binding names (kind="variable"), stdlib function references (kind="function"), builds reference lists.
- `_classify_tokens(tokens, ast) -> List[SemanticTokenData]` -- walks token stream and AST together, classifies each token span per the classification rules in the brainstorm.
- Records `analysis_time_ms` for performance monitoring.
- Catches all unexpected exceptions and wraps them in `FizzLSPAnalysisError`.

### Levenshtein distance utility
~20 lines. `_levenshtein(a: str, b: str) -> int` -- standard dynamic-programming edit distance. Used by the diagnostic publisher for typo suggestions and by the code action provider for similar-identifier fixes.

### _infer_type utility
~30 lines. `_infer_type(node) -> str` -- infers the type of an AST expression node. Integer literals -> "int", string literals -> "string", boolean literals -> "bool", arithmetic expressions -> "int", comparison expressions -> "bool", function calls -> function return type ("bool" for is_prime, "string" for fizzbuzz, "list" for range). Used by hover and completion providers.

---

## 10. Completion Provider (~400 lines)

### CompletionProvider
~350 lines. Implements `textDocument/completion`.

- `complete(uri: str, position: LSPPosition, context: Dict) -> List[CompletionItem]` -- determines completion context by analyzing cursor position relative to the token stream and partial AST.

**Completion contexts** (each a private method):

- `_complete_statement_level() -> List[CompletionItem]` -- at statement boundary: suggests `rule`, `let`, `evaluate` with snippet templates and tabstops.
  - `rule`: insert text `"rule ${1:name} when ${2:condition} emit ${3:expression} priority ${4:0}"`, format=SNIPPET
  - `let`: insert text `"let ${1:name} = ${2:expression}"`, format=SNIPPET
  - `evaluate`: insert text `"evaluate ${1:start} to ${2:end}"`, format=SNIPPET
- `_complete_keyword_sequence(preceding_tokens) -> List[CompletionItem]` -- after `rule NAME` suggests `when`; after `when EXPR` suggests `emit`; after `emit EXPR` suggests `priority`; after `evaluate N` suggests `to`.
- `_complete_variables(symbol_table, position) -> List[CompletionItem]` -- in expression context: all let-bound variables defined before cursor, the sacred variable `n`, booleans `true`/`false`.
- `_complete_functions() -> List[CompletionItem]` -- stdlib functions with signatures and documentation:
  - `is_prime(n)`: "Trial-division primality test. Returns true if n is prime."
  - `fizzbuzz(n)`: "Evaluate standard FizzBuzz for a single number. Returns the classification string."
  - `range(a, b)`: "Return integers from a to b inclusive."
- `_complete_operators() -> List[CompletionItem]` -- arithmetic (`+`,`-`,`*`,`/`,`%`), comparison (`==`,`!=`,`<`,`>`,`<=`,`>=`), boolean (`and`,`or`) operators.
- `_complete_fizzfile() -> List[CompletionItem]` -- when URI ends with `.fizzfile`: suggests `FROM`, `FIZZ`, `BUZZ`, `RUN`, `COPY`, `ENV`, `ENTRYPOINT`, `LABEL`, `EXPOSE`, `VOLUME`, `WORKDIR`, `USER`, `HEALTHCHECK`.
- `_complete_fizzgrammar() -> List[CompletionItem]` -- when URI ends with `.fizzgrammar` or content starts with BNF: suggests `::=`, `|`, `;`, `IDENTIFIER`, `NUMBER`, `STRING`, and non-terminal names from the FizzBuzz Classification grammar.
- `_determine_context(tokens, position) -> str` -- analyzes preceding tokens to determine which completion method to invoke ("statement", "keyword_after_rule", "keyword_after_when", "expression", "fizzfile", "fizzgrammar", etc.).

### CompletionResolveHandler
~50 lines. Implements `completionItem/resolve`. Lazily loads full documentation, additional text edits, and commit characters for a selected completion item.

---

## 11. Diagnostic Provider (~200 lines)

### DiagnosticPublisher
~120 lines. Converts `AnalysisResult.diagnostics` into LSP `textDocument/publishDiagnostics` notifications.

- `publish(uri: str, diagnostics: List[LSPDiagnostic]) -> LSPMessage` -- constructs the notification message with the diagnostic array serialized to LSP format.
- `_serialize_diagnostic(diag: LSPDiagnostic) -> Dict` -- converts to LSP dict format with range, severity, code, source, message, relatedInformation, tags.
- `_add_related_info(diag: LSPDiagnostic, symbol_table: SymbolTable)` -- for "undefined variable" errors: finds nearest identifier within Levenshtein distance 2, adds related location "Did you mean '...'?". For duplicate rule name errors: adds related location pointing to original definition.
- `_detect_unused_bindings(symbol_table: SymbolTable) -> List[LSPDiagnostic]` -- cross-references symbol table reference lists to find let-bindings with zero references. Produces HINT diagnostics with `Unnecessary` tag.
- `clear(uri: str) -> LSPMessage` -- publishes empty diagnostic array.
- Diagnostic code mapping:
  - `"EFP-FL11"`: lexer errors
  - `"EFP-FL12"`: parse errors
  - `"EFP-FL13"`: type errors
  - `"EFP-FL14"`: runtime errors (shown as warnings in static analysis)
  - `"EFP-LSP1"`: unused binding hints
  - `"EFP-LSP2"`: dependent type observations

### DiagnosticThrottler
~80 lines. Debounces diagnostic publication.

- `__init__(debounce_ms: int = DEFAULT_DIAGNOSTIC_DEBOUNCE_MS)`.
- `schedule(uri: str, callback: Callable)` -- records the callback and the current timestamp. If another schedule call arrives within `debounce_ms`, the previous callback is cancelled.
- `flush(uri: str)` -- immediately executes the pending callback for a URI (used during testing and on document close).
- `_pending: Dict[str, Tuple[float, Callable]]` -- pending callbacks keyed by URI.
- In simulation mode, debouncing is resolved synchronously by advancing logical time.

---

## 12. Go-to-Definition Provider (~200 lines)

### DefinitionProvider
~200 lines. Implements `textDocument/definition`.

- `definition(uri: str, position: LSPPosition, symbol_table: SymbolTable, ast: Any) -> Optional[LSPLocation]` -- identifies symbol under cursor, returns definition location.

**Resolution strategies** (each a private method):

- `_resolve_variable(name: str, symbol_table) -> LSPLocation` -- finds the `LetNode` where the variable was defined. Returns the position of the variable name in the `let` statement.
- `_resolve_rule(name: str, symbol_table) -> LSPLocation` -- finds the `RuleNode` where the rule was declared.
- `_resolve_stdlib_function(name: str) -> LSPLocation` -- returns a synthetic definition location representing the stdlib function. Resolves by introspecting `fizzlang.StdLib` to find the method (`is_prime`, `fizzbuzz`, `range_inclusive`). The synthetic location uses the URI `builtin:///fizzlang/stdlib` and the line number of the stdlib method definition.
- `_resolve_n() -> None` -- `n` has no definition site. Returns None.
- `_resolve_keyword() -> None` -- keywords are not user-defined. Returns None.
- `_find_token_at_position(tokens, position) -> Any` -- binary search through the token list to find the token whose source range contains the cursor position.
- `_classify_token_for_definition(token, ast) -> str` -- determines whether the token at the cursor is a variable reference, rule name, function call, `n`, or keyword, by cross-referencing with the AST node types.

---

## 13. Hover Provider (~300 lines)

### HoverProvider
~300 lines. Implements `textDocument/hover`.

- `hover(uri: str, position: LSPPosition, symbol_table: SymbolTable, ast: Any, tokens: List) -> Optional[Dict]` -- identifies entity under cursor, returns Hover response with Markdown content.

**Hover content generators** (each a private method):

- `_hover_variable(name: str, symbol_table) -> str` -- "(`variable`) NAME: TYPE\n\nDefined at line N: let NAME = EXPRESSION"
- `_hover_n() -> str` -- "(`intrinsic`) n: int\n\nThe number being evaluated. The only value that matters in FizzBuzz. All other variables exist in service of `n`."
- `_hover_stdlib_function(name: str) -> str` -- signature and documentation. e.g., "(`function`) is_prime(n: int) -> bool\n\nTrial-division primality test. O(sqrt(n)) because correctness demands it.\n\nArity: 1"
- `_hover_rule(name: str, symbol_table, ast) -> str` -- "(rule) NAME\n\nCondition: EXPR\nEmit: EXPR\nPriority: N"
- `_hover_keyword(keyword: str) -> str` -- documentation for each keyword:
  - `rule`: "Declares a FizzBuzz classification rule. Syntax: `rule NAME when CONDITION emit EXPRESSION [priority N]`"
  - `let`: "Binds a value to a name. Syntax: `let NAME = EXPRESSION`"
  - `evaluate`: "Evaluates a range of numbers through the declared rules. Syntax: `evaluate START to END`"
  - `when`, `emit`, `priority`, `to`, `and`, `or`, `not`: brief descriptions.
- `_hover_operator(op: str) -> str` -- semantics. `%` -> "Modulo operator. Returns the remainder of integer division. The single most important operator in FizzBuzz." `==` -> "Equality comparison. Returns `true` if both operands are equal." Etc.
- `_hover_integer_literal(value: int) -> str` -- "(`literal`) VALUE: int\n\nFizzBuzz classification: RESULT" -- actually evaluates the FizzBuzz classification for the literal value inline.

---

## 14. References Provider (~150 lines)

### ReferencesProvider
~150 lines. Implements `textDocument/references`.

- `references(uri: str, position: LSPPosition, include_declaration: bool, symbol_table: SymbolTable, ast: Any, tokens: List) -> List[LSPLocation]` -- collects all locations referencing the symbol at cursor.

- `_collect_variable_refs(name: str, ast, uri, include_declaration) -> List[LSPLocation]` -- walks AST collecting all `IdentifierNode` nodes matching name. If `include_declaration`, includes the `LetNode` definition.
- `_collect_rule_refs(name: str, ast, tokens, uri, include_declaration) -> List[LSPLocation]` -- collects rule declaration. Scans comment tokens for word-boundary matches of the rule name.
- `_collect_function_refs(name: str, ast, uri, include_declaration) -> List[LSPLocation]` -- collects all `FunctionCallNode` nodes matching name. If `include_declaration`, includes synthetic stdlib location.
- `_collect_n_refs(ast, uri) -> List[LSPLocation]` -- collects all `NVarNode` nodes. No declaration site.

---

## 15. Rename Provider (~250 lines)

### RenameProvider
~250 lines. Implements `textDocument/rename` and `textDocument/prepareRename`.

- `prepare_rename(uri: str, position: LSPPosition, symbol_table: SymbolTable, tokens: List) -> Optional[Dict]` -- validates renameability. Returns `{ range, placeholder }` or error.
  - Renameable: variables, rule names.
  - Not renameable: keywords, operators, literals, `n` ("Cannot rename the sacred variable 'n'. It is immutable in name as in purpose."), stdlib functions ("Cannot rename stdlib function '...'. The standard library is a covenant, not a suggestion.").

- `rename(uri: str, position: LSPPosition, new_name: str, symbol_table: SymbolTable, ast: Any, tokens: List) -> WorkspaceEdit` -- computes all text edits.
  - `_validate_identifier(name: str)` -- must start with letter or underscore, alphanumeric + underscores only, not a reserved keyword, not `n`. Raises `FizzLSPRenameError`.
  - `_check_conflicts(new_name: str, symbol_table: SymbolTable)` -- checks existing let-bindings, rule names, stdlib names. Raises `FizzLSPRenameConflictError` with conflict location.
  - Collects all reference locations via `ReferencesProvider` (include_declaration=True).
  - For rule names: also scans comment text for word-boundary matches and produces edits for those occurrences.
  - Produces `WorkspaceEdit` with `TextEdit` for each occurrence.

---

## 16. Workspace Symbol Provider (~100 lines)

### WorkspaceSymbolProvider
~100 lines. Implements `workspace/symbol`.

- `symbols(query: str, document_manager: TextDocumentManager, analysis_cache: Dict) -> List[Dict]` -- searches all open documents' symbol tables.
- Case-insensitive substring matching.
- Empty query returns all symbols.
- Returns `SymbolInformation` objects with: name, kind (rule -> Function, let-binding -> Variable, evaluate -> Event, stdlib -> Method), location, container name (document filename).

---

## 17. Semantic Token Provider (~250 lines)

### SemanticTokenProvider
~250 lines. Implements `textDocument/semanticTokens/full` and `textDocument/semanticTokens/range`.

- `full(uri: str, semantic_tokens: List[SemanticTokenData]) -> Dict` -- encodes all tokens in LSP delta-encoded format (5 integers per token: delta line, delta start character, length, token type index, token modifier bitset).
- `range(uri: str, range: LSPRange, semantic_tokens: List[SemanticTokenData]) -> Dict` -- filters tokens to requested range, then delta-encodes.
- `_delta_encode(tokens: List[SemanticTokenData]) -> List[int]` -- sorts tokens by (line, start_char), computes deltas.
- `_get_legend() -> Dict` -- returns the token type and modifier legends for capability declaration.

**Classification rules** (applied during analysis pipeline, implemented in `_classify_tokens`):
- FizzLang keywords (RULE, WHEN, EMIT, EVALUATE, TO, LET, PRIORITY, AND, OR, NOT, TRUE, FALSE) -> `keyword`
- N_VAR -> `variable` + `readonly` modifier
- IDENTIFIER at LetNode.name -> `variable` + `declaration` modifier
- IDENTIFIER at IdentifierNode reference -> `variable`
- IDENTIFIER at RuleNode.name -> `function` + `declaration` modifier
- IDENTIFIER at FunctionCallNode.name -> `function` + `defaultLibrary` modifier
- INTEGER -> `number`
- STRING -> `string`
- Operators (+, -, *, /, %, ==, !=, <, >, <=, >=, =) -> `operator`
- Comment lines (#) -> `comment`

---

## 18. Code Action Provider (~250 lines)

### CodeActionProvider
~250 lines. Implements `textDocument/codeAction`.

- `code_actions(uri: str, range: LSPRange, diagnostics: List[LSPDiagnostic], symbol_table: SymbolTable, ast: Any, source: str) -> List[Dict]`.

**Quick fixes:**
- `_fix_similar_identifier(diag, symbol_table) -> Dict` -- when undefined variable error, and a symbol within Levenshtein distance 2 exists: "Replace 'TYPO' with 'CORRECT'" code action replacing the reference.
- `_fix_add_let_binding(diag, source) -> Dict` -- when undefined variable: insert `let NAME = PLACEHOLDER` before the line. Placeholder is `0` for arithmetic context, `""` for string context, `true` for boolean context.
- `_fix_duplicate_rule_name(diag, source) -> Dict` -- when duplicate rule name: append numeric suffix ("fizz" -> "fizz_2").
- `_fix_negative_priority(diag, source) -> Dict` -- when negative priority: change to 0.

**Refactoring:**
- `_refactor_extract_expression(range, ast, source) -> Optional[Dict]` -- when cursor is on an expression appearing more than once: extract to `let` binding. Variable name derived from expression (e.g., `n % 3` -> `n_mod_3`).
- `_refactor_reorder_rules(ast, source) -> Optional[Dict]` -- when rules are not ordered by priority: reorder in descending priority order.

**Source:**
- `_source_format_document(uri, source) -> Dict` -- equivalent to formatting, offered as a code action.

---

## 19. Document Formatting Provider (~150 lines)

### FormattingProvider
~150 lines. Implements `textDocument/formatting`.

- `format(uri: str, tokens: List, source: str) -> List[TextEdit]` -- produces edits transforming to canonical FizzLang style.

**Formatting rules** (operates on token stream):
- Exactly one blank line between statements. No blank lines within a statement. No leading/trailing blank lines.
- Zero indentation (FizzLang has no block structure).
- Single space between keywords and arguments.
- Single space around operators.
- No space inside parentheses. No space before commas. Single space after commas.
- Keywords canonicalized to lowercase.
- Trailing whitespace removed.
- Document ends with exactly one newline.
- `_reformat_tokens(tokens) -> str` -- re-emits tokens with canonical spacing.
- `_compute_edits(original: str, formatted: str) -> List[TextEdit]` -- diff-based minimal edit computation.

---

## 20. Document Symbol Provider (~100 lines)

### DocumentSymbolProvider
~100 lines. Implements `textDocument/documentSymbol`.

- `symbols(uri: str, ast: Any) -> List[DocumentSymbol]` -- walks AST producing hierarchical outline.
  - **Rules**: `SymbolKind.FUNCTION`, detail = condition + emit, children = condition (BOOLEAN), emit (STRING), priority (NUMBER).
  - **Let-bindings**: `SymbolKind.VARIABLE`, detail = bound expression.
  - **Evaluate statements**: `SymbolKind.EVENT`, detail = range expression.

---

## 21. FizzLSP Server (~150 lines)

### FizzLSPServer
~150 lines. The top-level server class wiring everything together.

- `__init__(transport_type, tcp_port, debounce_ms, max_completion_items, semantic_tokens_enabled, dependent_type_diagnostics)`.
- `_state: LSPServerState` initialized to UNINITIALIZED.
- `_transport: LSPTransport` -- constructed based on transport_type.
- `_dispatcher: LSPDispatcher` -- registers all handlers.
- `_doc_manager: TextDocumentManager`.
- `_pipeline: AnalysisPipeline`.
- `_analysis_cache: Dict[str, AnalysisResult]` -- caches latest analysis per URI.
- `_completion_provider: CompletionProvider`.
- `_diagnostic_publisher: DiagnosticPublisher`.
- `_diagnostic_throttler: DiagnosticThrottler`.
- `_definition_provider: DefinitionProvider`.
- `_hover_provider: HoverProvider`.
- `_references_provider: ReferencesProvider`.
- `_rename_provider: RenameProvider`.
- `_workspace_symbol_provider: WorkspaceSymbolProvider`.
- `_semantic_token_provider: SemanticTokenProvider`.
- `_code_action_provider: CodeActionProvider`.
- `_formatting_provider: FormattingProvider`.
- `_document_symbol_provider: DocumentSymbolProvider`.
- `_metrics: FizzLSPMetrics`.
- `_client_capabilities: Dict` -- stored during initialize.

**Methods:**
- `handle_message(raw: str) -> Optional[str]` -- decodes incoming message, validates server state, dispatches to handler, encodes response. Returns None for notifications requiring no response.
- `simulate_session(messages: List[str]) -> List[str]` -- processes a sequence of raw LSP messages, returns responses and notifications. Primary testing interface.
- `_register_handlers()` -- registers all LSP method handlers with the dispatcher:
  - `initialize`, `initialized`, `shutdown`, `exit`
  - `textDocument/didOpen`, `textDocument/didChange`, `textDocument/didClose`
  - `textDocument/completion`, `completionItem/resolve`
  - `textDocument/hover`, `textDocument/definition`, `textDocument/references`
  - `textDocument/rename`, `textDocument/prepareRename`
  - `workspace/symbol`
  - `textDocument/semanticTokens/full`, `textDocument/semanticTokens/range`
  - `textDocument/codeAction`, `textDocument/formatting`, `textDocument/documentSymbol`
- `_on_document_change(uri: str)` -- runs analysis pipeline, updates cache, schedules diagnostic publication.

---

## 22. FizzLSP Dashboard (~100 lines)

### FizzLSPDashboard
~100 lines. ASCII dashboard with box-drawing characters.

- `render(server: FizzLSPServer, width: int = DEFAULT_DASHBOARD_WIDTH, ...) -> str` -- renders:
  - Server state and uptime.
  - Connected client capabilities summary.
  - Active documents: URI, version, symbol count, diagnostic count.
  - Total symbols: rules, variables, evaluate statements.
  - Diagnostic breakdown: errors, warnings, information, hints.
  - Protocol statistics: requests received, responses sent, notifications sent, average response latency.
  - The LSP Complexity Index: lines of `fizzlsp.py` divided by lines of core FizzBuzz logic.

---

## 23. CLI Integration (~80 lines)

Integrated into the `FizzLSPFeature.run_early_exit()` method and the main server.

**CLI flags** (registered in `FizzLSPFeature`):
- `--fizzlsp`: enable the FizzLSP language server subsystem.
- `--fizzlsp-analyze <FILE>`: run full analysis pipeline on a FizzLang file, print diagnostics, symbol table, semantic tokens.
- `--fizzlsp-complete <FILE> <LINE> <COL>`: simulate completion at position, print completion list.
- `--fizzlsp-hover <FILE> <LINE> <COL>`: simulate hover, print hover content.
- `--fizzlsp-definition <FILE> <LINE> <COL>`: simulate go-to-definition, print location.
- `--fizzlsp-references <FILE> <LINE> <COL>`: simulate find-references, print locations.
- `--fizzlsp-rename <FILE> <LINE> <COL> <NEW_NAME>`: simulate rename, print workspace edit.
- `--fizzlsp-format <FILE>`: simulate formatting, print formatted document.
- `--fizzlsp-symbols <FILE>`: print document symbol outline.
- `--fizzlsp-tokens <FILE>`: print semantic token classifications.
- `--fizzlsp-simulate`: run predefined editor simulation session.
- `--fizzlsp-metrics`: print performance metrics.
- `--fizzlsp-dashboard`: display ASCII dashboard.

---

## 24. Middleware Integration (~50 lines)

### FizzLSPMiddleware
~50 lines. Implements `IMiddleware`.

- `process(context: ProcessingContext) -> ProcessingContext` -- records language server activity during FizzBuzz evaluation: server state, number of open documents, total diagnostic count, analysis pipeline latency. Adds `fizzlsp_state`, `fizzlsp_open_documents`, `fizzlsp_total_diagnostics`, `fizzlsp_avg_analysis_ms` to the processing context metadata.
- When the feature is disabled, reports `"FizzLSP: disabled"`.

---

## 25. Supporting Files

### exceptions: `enterprise_fizzbuzz/domain/exceptions/fizzlsp.py`

~200 lines. Exception hierarchy with EFP-LSP prefix codes.

```python
class FizzLSPError(FizzBuzzError):
    """Base exception for all FizzLSP Language Server Protocol errors.

    The Language Server Protocol was designed to help developers write code
    faster.  FizzLang programs average 8 lines.  The typical developer writes
    a FizzLang program in under 30 seconds.  The LSP infrastructure required
    to provide IDE intelligence for those 30 seconds exceeds 3,500 lines.
    Every FizzLSP error is therefore a failure of tooling that costs 100x
    more than the artifact it supports.  This is the correct ratio for
    enterprise software.
    """
    # error_code="EFP-LSP0"

class FizzLSPTransportError(FizzLSPError):
    """Raised when the JSON-RPC transport layer encounters a framing or
    encoding error.  The Content-Length header said 247 bytes.  The body
    contained 246 bytes.  One byte separates a well-formed message from
    a protocol violation.  The wire does not negotiate."""
    # error_code="EFP-LSP1"

class FizzLSPProtocolError(FizzLSPError):
    """Raised when the server state machine rejects a transition.
    UNINITIALIZED servers do not serve completions.  TERMINATED servers
    do not serve anything.  The protocol has opinions."""
    # error_code="EFP-LSP2"

class FizzLSPSessionError(FizzLSPError):
    """Raised when an initialization or shutdown handshake fails."""
    # error_code="EFP-LSP3"

class FizzLSPDocumentError(FizzLSPError):
    """Raised when a document operation targets a URI that is not open
    or is already open."""
    # error_code="EFP-LSP4"

class FizzLSPDocumentSyncError(FizzLSPError):
    """Raised when incremental document synchronization fails.  The client
    sent a range that extends beyond the document boundary.  The document
    has 12 lines.  The edit starts at line 15.  The client and server
    disagree about reality."""
    # error_code="EFP-LSP5"

class FizzLSPAnalysisError(FizzLSPError):
    """Raised when the analysis pipeline encounters an unexpected error
    during lexing, parsing, type checking, or symbol collection."""
    # error_code="EFP-LSP6"

class FizzLSPCompletionError(FizzLSPError):
    """Raised when completion context analysis or item generation fails."""
    # error_code="EFP-LSP7"

class FizzLSPDiagnosticError(FizzLSPError):
    """Raised when diagnostic publication or serialization fails."""
    # error_code="EFP-LSP8"

class FizzLSPDefinitionError(FizzLSPError):
    """Raised when go-to-definition resolution encounters an error."""
    # error_code="EFP-LSP9"

class FizzLSPHoverError(FizzLSPError):
    """Raised when hover content generation fails."""
    # error_code="EFP-LSP10"

class FizzLSPReferencesError(FizzLSPError):
    """Raised when find-all-references encounters an error during
    AST traversal or comment scanning."""
    # error_code="EFP-LSP11"

class FizzLSPRenameError(FizzLSPError):
    """Raised when a rename operation fails validation.  The new name
    is a reserved keyword, or is 'n', or violates identifier syntax."""
    # error_code="EFP-LSP12"

class FizzLSPRenameConflictError(FizzLSPRenameError):
    """Raised when a rename would create a name conflict with an
    existing symbol."""
    # error_code="EFP-LSP13"

class FizzLSPSemanticTokenError(FizzLSPError):
    """Raised when semantic token classification or delta encoding fails."""
    # error_code="EFP-LSP14"

class FizzLSPCodeActionError(FizzLSPError):
    """Raised when code action computation fails."""
    # error_code="EFP-LSP15"

class FizzLSPFormattingError(FizzLSPError):
    """Raised when document formatting fails."""
    # error_code="EFP-LSP16"

class FizzLSPSymbolError(FizzLSPError):
    """Raised when document or workspace symbol resolution fails."""
    # error_code="EFP-LSP17"

class FizzLSPDispatchError(FizzLSPError):
    """Raised when the dispatcher encounters a handler registration
    conflict or dispatch failure."""
    # error_code="EFP-LSP18"

class FizzLSPMiddlewareError(FizzLSPError):
    """Raised when the FizzLSP middleware component fails during
    FizzBuzz evaluation context recording."""
    # error_code="EFP-LSP19"
```

### events: `enterprise_fizzbuzz/domain/events/fizzlsp.py`

~20 lines. Event type registrations.

```python
"""FizzLSP Language Server Protocol events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("LSP_SERVER_INITIALIZED")
EventType.register("LSP_SERVER_SHUTDOWN")
EventType.register("LSP_DOCUMENT_OPENED")
EventType.register("LSP_DOCUMENT_CHANGED")
EventType.register("LSP_DOCUMENT_CLOSED")
EventType.register("LSP_DIAGNOSTICS_PUBLISHED")
EventType.register("LSP_COMPLETION_SERVED")
EventType.register("LSP_DEFINITION_RESOLVED")
EventType.register("LSP_HOVER_SERVED")
EventType.register("LSP_RENAME_PERFORMED")
EventType.register("LSP_DASHBOARD_RENDERED")
```

### config mixin: `enterprise_fizzbuzz/infrastructure/config/mixins/fizzlsp.py`

~80 lines. Configuration properties following the FizzdapConfigMixin pattern.

```python
class FizzlspConfigMixin:
    """Configuration properties for the fizzlsp subsystem."""

    @property
    def fizzlsp_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("enabled", False)

    @property
    def fizzlsp_transport(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("transport", "stdio")

    @property
    def fizzlsp_tcp_port(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("tcp_port", 5007)

    @property
    def fizzlsp_diagnostic_debounce_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("diagnostic_debounce_ms", 150)

    @property
    def fizzlsp_max_completion_items(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("max_completion_items", 50)

    @property
    def fizzlsp_semantic_tokens_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("semantic_tokens_enabled", True)

    @property
    def fizzlsp_dependent_type_diagnostics(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("dependent_type_diagnostics", True)

    @property
    def fizzlsp_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("dashboard", {}).get("width", 60)

    @property
    def fizzlsp_dashboard_show_documents(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("dashboard", {}).get("show_documents", True)

    @property
    def fizzlsp_dashboard_show_diagnostics(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("dashboard", {}).get("show_diagnostics", True)

    @property
    def fizzlsp_dashboard_show_protocol_stats(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("dashboard", {}).get("show_protocol_stats", True)

    @property
    def fizzlsp_dashboard_show_complexity_index(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlsp", {}).get("dashboard", {}).get("show_complexity_index", True)
```

### feature descriptor: `enterprise_fizzbuzz/infrastructure/features/fizzlsp_feature.py`

~100 lines. Following the FizzDAPFeature pattern.

```python
class FizzLSPFeature(FeatureDescriptor):
    name = "fizzlsp"
    description = "Language Server Protocol server for FizzLang with completions, diagnostics, hover, definition, rename, and semantic tokens"
    middleware_priority = 92
    cli_flags = [
        ("--fizzlsp", {"action": "store_true", "default": False,
                       "help": "Enable the FizzLSP Language Server Protocol server"}),
        ("--fizzlsp-analyze", {"type": str, "metavar": "FILE", "default": None,
                               "help": "Run the full LSP analysis pipeline on a FizzLang file and print diagnostics"}),
        ("--fizzlsp-complete", {"type": str, "nargs": 3, "metavar": ("FILE", "LINE", "COL"), "default": None,
                                "help": "Simulate a completion request at the given cursor position"}),
        ("--fizzlsp-hover", {"type": str, "nargs": 3, "metavar": ("FILE", "LINE", "COL"), "default": None,
                             "help": "Simulate a hover request and print hover content"}),
        ("--fizzlsp-definition", {"type": str, "nargs": 3, "metavar": ("FILE", "LINE", "COL"), "default": None,
                                  "help": "Simulate a go-to-definition request"}),
        ("--fizzlsp-references", {"type": str, "nargs": 3, "metavar": ("FILE", "LINE", "COL"), "default": None,
                                  "help": "Simulate a find-references request"}),
        ("--fizzlsp-rename", {"type": str, "nargs": 4, "metavar": ("FILE", "LINE", "COL", "NEW_NAME"), "default": None,
                              "help": "Simulate a rename request and print the workspace edit"}),
        ("--fizzlsp-format", {"type": str, "metavar": "FILE", "default": None,
                              "help": "Format a FizzLang file according to canonical style"}),
        ("--fizzlsp-symbols", {"type": str, "metavar": "FILE", "default": None,
                               "help": "Print the document symbol outline for a FizzLang file"}),
        ("--fizzlsp-tokens", {"type": str, "metavar": "FILE", "default": None,
                              "help": "Print semantic token classifications for every token"}),
        ("--fizzlsp-simulate", {"action": "store_true", "default": False,
                                "help": "Run a predefined editor simulation session with full JSON-RPC message exchange"}),
        ("--fizzlsp-metrics", {"action": "store_true", "default": False,
                               "help": "Print FizzLSP performance metrics"}),
        ("--fizzlsp-dashboard", {"action": "store_true", "default": False,
                                 "help": "Display the FizzLSP ASCII dashboard"}),
    ]

    def is_enabled(self, args):
        return any([
            getattr(args, "fizzlsp", False),
            getattr(args, "fizzlsp_analyze", None) is not None,
            getattr(args, "fizzlsp_complete", None) is not None,
            getattr(args, "fizzlsp_hover", None) is not None,
            getattr(args, "fizzlsp_definition", None) is not None,
            getattr(args, "fizzlsp_references", None) is not None,
            getattr(args, "fizzlsp_rename", None) is not None,
            getattr(args, "fizzlsp_format", None) is not None,
            getattr(args, "fizzlsp_symbols", None) is not None,
            getattr(args, "fizzlsp_tokens", None) is not None,
            getattr(args, "fizzlsp_simulate", False),
            getattr(args, "fizzlsp_dashboard", False),
        ])

    def has_early_exit(self, args):
        return any([
            getattr(args, "fizzlsp_analyze", None) is not None,
            getattr(args, "fizzlsp_complete", None) is not None,
            getattr(args, "fizzlsp_hover", None) is not None,
            getattr(args, "fizzlsp_definition", None) is not None,
            getattr(args, "fizzlsp_references", None) is not None,
            getattr(args, "fizzlsp_rename", None) is not None,
            getattr(args, "fizzlsp_format", None) is not None,
            getattr(args, "fizzlsp_symbols", None) is not None,
            getattr(args, "fizzlsp_tokens", None) is not None,
            getattr(args, "fizzlsp_simulate", False),
        ])

    def run_early_exit(self, args, config):
        # Imports FizzLSPServer from fizzlsp.py, constructs server,
        # dispatches to the appropriate CLI subcommand. Each subcommand
        # reads the file, opens the document via simulate_session(),
        # performs the requested operation, and prints the result.
        ...

    def create(self, config, args, event_bus=None):
        # Creates FizzLSPServer with config properties, returns (server, middleware)
        ...

    def render(self, middleware, args):
        # Renders dashboard if --fizzlsp-dashboard
        ...
```

### config file: `config.d/fizzlsp.yaml`

```yaml
# FizzLSP Language Server Protocol Configuration
# The Language Server Protocol was designed to help developers write code
# faster.  FizzLang programs average 8 lines and take under 30 seconds
# to write.  The LSP infrastructure providing IDE intelligence for those
# 30 seconds exceeds 3,500 lines of protocol handling, analysis pipeline,
# completion engine, diagnostic publisher, semantic token classifier,
# code action provider, and formatting engine.  This configuration file
# controls the 3,500 lines that serve the 8.
fizzlsp:
  enabled: false                          # Master switch -- opt-in via --fizzlsp
  transport: "stdio"                      # Transport type: "stdio" or "tcp"
  tcp_port: 5007                          # TCP port for the TCP transport (simulated)
  diagnostic_debounce_ms: 150             # Debounce interval for diagnostic publication
  max_completion_items: 50                # Maximum completion items per request
  semantic_tokens_enabled: true           # Whether to compute semantic tokens
  dependent_type_diagnostics: true        # Include dependent type observations in diagnostics
  dashboard:
    width: 60                             # ASCII dashboard width
    show_documents: true                  # Show active documents table
    show_diagnostics: true                # Show diagnostic breakdown
    show_protocol_stats: true             # Show protocol statistics
    show_complexity_index: true           # Show LSP Complexity Index
```

### re-export stub: `fizzlsp.py` (root)

```python
"""Backward-compatible re-export stub for fizzlsp."""
from enterprise_fizzbuzz.infrastructure.fizzlsp import *  # noqa: F401,F403
```

---

## 26. Test Plan: `tests/test_fizzlsp.py` (~500 lines, ~100 tests)

### Test structure
All tests use pytest with per-file fixtures. No conftest.py. Singletons reset via `_SingletonMeta.reset()`.

### Fixtures
- `lsp_server()` -- creates a `FizzLSPServer` with default config.
- `initialized_server()` -- creates server, processes initialize + initialized handshake.
- `sample_source()` -- returns a sample FizzLang program:
  ```
  let divisor = 3
  rule fizz when n % divisor == 0 emit "Fizz" priority 1
  rule buzz when n % 5 == 0 emit "Buzz" priority 1
  evaluate 1 to 20
  ```
- `server_with_doc(initialized_server, sample_source)` -- opens the sample source as a document.
- `make_request(method, params, id)` -- helper constructing JSON-RPC request messages.
- `make_notification(method, params)` -- helper constructing notification messages.

### Test Classes

**TestLSPMessage** (~8 tests)
- `test_encode_request` -- encode a request, verify Content-Length header and JSON body.
- `test_encode_notification` -- encode a notification (no id).
- `test_decode_valid` -- decode from wire format.
- `test_decode_missing_content_length` -- raises FizzLSPTransportError.
- `test_decode_truncated_body` -- raises FizzLSPTransportError.
- `test_decode_invalid_json` -- raises FizzLSPTransportError.
- `test_message_type_classification` -- request vs response vs notification.
- `test_content_length_utf8` -- Content-Length computed from UTF-8 bytes.

**TestLSPTransport** (~6 tests)
- `test_stdio_send_receive` -- round-trip through StdioTransport.
- `test_tcp_send_receive` -- round-trip through TCPTransport.
- `test_stdio_empty_input` -- receive returns None on exhausted buffer.
- `test_tcp_multiple_messages` -- send/receive multiple messages in sequence.
- `test_stdio_large_message` -- message with large params dict.
- `test_tcp_interleaved` -- client and server messages interleaved.

**TestLSPDispatcher** (~6 tests)
- `test_dispatch_request` -- handler called, response returned.
- `test_dispatch_notification` -- handler called, no response.
- `test_dispatch_unknown_method` -- MethodNotFound error response.
- `test_dispatch_handler_exception` -- InternalError response.
- `test_register_duplicate` -- raises FizzLSPDispatchError.
- `test_dispatch_logging` -- messages logged for debugging.

**TestInitializationHandshake** (~8 tests)
- `test_initialize_returns_capabilities` -- verify all capabilities in response.
- `test_initialize_stores_client_capabilities` -- client caps stored.
- `test_initialized_transitions_to_running` -- state transitions.
- `test_request_before_initialize` -- ServerNotInitialized error.
- `test_double_initialize` -- error on second initialize.
- `test_shutdown_transitions_state` -- RUNNING -> SHUTTING_DOWN.
- `test_exit_after_shutdown` -- exit code 0.
- `test_exit_without_shutdown` -- exit code 1.

**TestDocumentSync** (~8 tests)
- `test_did_open_creates_document` -- document stored with content.
- `test_did_open_triggers_analysis` -- diagnostics published after open.
- `test_did_change_incremental` -- applies text range changes.
- `test_did_change_multi_line` -- edits spanning multiple lines.
- `test_did_change_version_tracking` -- version incremented.
- `test_did_close_removes_document` -- document removed, diagnostics cleared.
- `test_did_open_duplicate` -- error on opening already-open document.
- `test_did_change_out_of_bounds` -- error on edit beyond document boundary.

**TestCompletion** (~12 tests)
- `test_statement_level_completions` -- rule, let, evaluate suggested.
- `test_keyword_after_rule_name` -- when suggested.
- `test_keyword_after_when` -- emit suggested.
- `test_keyword_after_emit` -- priority suggested.
- `test_keyword_after_evaluate` -- to suggested.
- `test_variable_completions` -- let-bound variables and n suggested.
- `test_function_completions` -- is_prime, fizzbuzz, range suggested with docs.
- `test_operator_completions` -- arithmetic and comparison operators.
- `test_completion_snippets` -- snippet templates with tabstops.
- `test_completion_sort_order` -- keywords before variables before functions.
- `test_completion_resolve` -- lazy documentation loading.
- `test_max_completion_items` -- respects configured maximum.

**TestDiagnostics** (~10 tests)
- `test_lexer_error_diagnostic` -- unrecognized character -> ERROR.
- `test_parse_error_diagnostic` -- unexpected token -> ERROR with expected info.
- `test_type_error_undefined_variable` -- undefined var -> ERROR with related info.
- `test_type_error_duplicate_rule` -- duplicate rule -> ERROR with original location.
- `test_dependent_type_observation` -- proof obligation -> INFORMATION.
- `test_unused_binding_hint` -- unused let -> HINT with Unnecessary tag.
- `test_empty_program_warning` -- empty source -> WARNING.
- `test_diagnostic_debounce` -- multiple rapid changes produce single publication.
- `test_diagnostic_codes` -- correct EFP codes for each error type.
- `test_diagnostic_clear_on_close` -- empty diagnostics on document close.

**TestDefinition** (~6 tests)
- `test_definition_variable` -- navigate to let-binding.
- `test_definition_rule` -- navigate to rule declaration.
- `test_definition_stdlib_function` -- navigate to synthetic stdlib location.
- `test_definition_n_returns_none` -- n has no definition site.
- `test_definition_keyword_returns_none` -- keywords not user-defined.
- `test_definition_out_of_range` -- cursor beyond document returns None.

**TestHover** (~8 tests)
- `test_hover_variable` -- shows type and definition.
- `test_hover_n` -- shows intrinsic documentation.
- `test_hover_stdlib_function` -- shows signature and documentation.
- `test_hover_rule` -- shows condition, emit, priority.
- `test_hover_keyword` -- shows keyword documentation.
- `test_hover_operator` -- shows operator semantics.
- `test_hover_integer_literal` -- shows FizzBuzz classification.
- `test_hover_whitespace_returns_none` -- no hover on empty space.

**TestReferences** (~5 tests)
- `test_references_variable` -- all IdentifierNode occurrences.
- `test_references_variable_include_declaration` -- includes LetNode.
- `test_references_rule` -- includes declaration and comments.
- `test_references_n` -- all NVarNode occurrences.
- `test_references_stdlib_function` -- all FunctionCallNode occurrences.

**TestRename** (~8 tests)
- `test_prepare_rename_variable` -- returns range and placeholder.
- `test_prepare_rename_n_rejected` -- cannot rename n.
- `test_prepare_rename_keyword_rejected` -- cannot rename keywords.
- `test_rename_variable_all_occurrences` -- all references updated.
- `test_rename_rule_all_occurrences` -- rule name + comment references updated.
- `test_rename_conflict_detection` -- existing name -> error.
- `test_rename_invalid_identifier` -- reserved keyword -> error.
- `test_rename_to_n_rejected` -- cannot rename to 'n'.

**TestSemanticTokens** (~5 tests)
- `test_semantic_tokens_full` -- all tokens classified correctly.
- `test_semantic_tokens_range` -- only range-filtered tokens returned.
- `test_semantic_token_delta_encoding` -- deltas computed correctly.
- `test_keyword_token_type` -- keywords classified as keyword.
- `test_n_token_readonly_modifier` -- n has readonly modifier.

**TestCodeActions** (~6 tests)
- `test_quickfix_similar_identifier` -- typo suggestion offered.
- `test_quickfix_add_let_binding` -- insert let binding for undefined var.
- `test_quickfix_duplicate_rule` -- numeric suffix offered.
- `test_quickfix_negative_priority` -- change to 0 offered.
- `test_refactor_extract_expression` -- repeated expression extracted.
- `test_refactor_reorder_rules` -- rules reordered by priority.

**TestFormatting** (~5 tests)
- `test_format_spacing` -- canonical spacing applied.
- `test_format_blank_lines` -- exactly one between statements.
- `test_format_trailing_whitespace` -- stripped.
- `test_format_keyword_case` -- lowercased.
- `test_format_final_newline` -- exactly one.

**TestDocumentSymbols** (~3 tests)
- `test_document_symbols_rules` -- rules as Function with children.
- `test_document_symbols_let_bindings` -- let-bindings as Variable.
- `test_document_symbols_evaluate` -- evaluate as Event.

**TestWorkspaceSymbols** (~3 tests)
- `test_workspace_symbols_all` -- empty query returns all.
- `test_workspace_symbols_filter` -- substring filter.
- `test_workspace_symbols_case_insensitive` -- case insensitive match.

**TestIntegration** (~3 tests)
- `test_full_editor_session` -- open, edit, complete, hover, definition, rename, close.
- `test_simulate_session` -- predefined message sequence.
- `test_dashboard_render` -- dashboard produces valid ASCII output.

---

## 27. Full File Inventory

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `enterprise_fizzbuzz/infrastructure/fizzlsp.py` | ~3,500 | Main LSP implementation |
| 2 | `tests/test_fizzlsp.py` | ~500 | Test suite (~100 tests) |
| 3 | `enterprise_fizzbuzz/domain/exceptions/fizzlsp.py` | ~200 | 20 exception classes (EFP-LSP0..EFP-LSP19) |
| 4 | `enterprise_fizzbuzz/domain/events/fizzlsp.py` | ~20 | 11 event type registrations |
| 5 | `enterprise_fizzbuzz/infrastructure/config/mixins/fizzlsp.py` | ~80 | 12 configuration properties |
| 6 | `enterprise_fizzbuzz/infrastructure/features/fizzlsp_feature.py` | ~100 | Feature descriptor with 13 CLI flags |
| 7 | `config.d/fizzlsp.yaml` | ~20 | YAML configuration with defaults |
| 8 | `fizzlsp.py` | ~2 | Root-level re-export stub |

**Total: ~4,422 lines across 8 files**

---

## 28. Integration Touchpoints (EXISTING files that need modification)

| File | Change |
|------|--------|
| `enterprise_fizzbuzz/domain/exceptions/__init__.py` | Add imports for all `FizzLSP*` exceptions |
| `enterprise_fizzbuzz/domain/events/__init__.py` | Add `import enterprise_fizzbuzz.domain.events.fizzlsp` |
| `enterprise_fizzbuzz/infrastructure/config/mixins/__init__.py` | Add `FizzlspConfigMixin` to mixin imports (if __init__ exists) |
| `enterprise_fizzbuzz/infrastructure/config/manager.py` | Add `FizzlspConfigMixin` to ConfigurationManager bases (if mixin pattern requires) |
| `enterprise_fizzbuzz/infrastructure/features/__init__.py` | Register `FizzLSPFeature` (if feature registry requires) |

---

## 29. Dependency Map

```
fizzlsp.py
  ├── domain/exceptions/fizzlsp.py      (FizzLSP* exceptions)
  ├── domain/events/fizzlsp.py          (LSP_* event types)
  ├── domain/interfaces.py              (IMiddleware)
  ├── domain/models.py                  (EventType, FizzBuzzResult, ProcessingContext)
  ├── infrastructure/fizzlang.py        (Lexer, Parser, TypeChecker, StdLib, TokenType, AST nodes)
  ├── infrastructure/dependent_types.py (TypeCheckError, ProofObligationError, UnificationError)
  └── infrastructure/fizzlang.py        (Grammar, Symbol for FizzGrammar completions)
```

All dependencies point inward (infrastructure -> domain) or are peer infrastructure imports. The Dependency Rule is maintained.

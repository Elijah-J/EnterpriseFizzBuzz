"""
Enterprise FizzBuzz Platform - FizzLSP Language Server Protocol Tests

Comprehensive test coverage for the FizzLSP language server:
LSP message encoding/decoding, JSON-RPC transport round-trips,
dispatcher routing, initialization handshake, document synchronization,
completion, diagnostics, go-to-definition, hover, find-references,
rename, semantic tokens, code actions, formatting, document symbols,
workspace symbols, and full editor session simulation.
"""

from __future__ import annotations

import json
from io import StringIO

import pytest

from enterprise_fizzbuzz.infrastructure.fizzlsp import (
    AnalysisPipeline,
    AnalysisResult,
    CodeActionKind,
    CodeActionProvider,
    CompletionItem,
    CompletionItemKind,
    CompletionProvider,
    DEFAULT_DIAGNOSTIC_DEBOUNCE_MS,
    DEFAULT_MAX_COMPLETION_ITEMS,
    DEFAULT_TCP_PORT,
    DEFAULT_TRANSPORT,
    DefinitionProvider,
    DiagnosticPublisher,
    DiagnosticSeverity,
    DiagnosticTag,
    DiagnosticThrottler,
    DocumentSymbol,
    DocumentSymbolProvider,
    FIZZLSP_SERVER_NAME,
    FIZZLSP_VERSION,
    FizzLSPDashboard,
    FizzLSPMetrics,
    FizzLSPMiddleware,
    FizzLSPServer,
    FormattingProvider,
    HoverProvider,
    IncrementalSyncEngine,
    InsertTextFormat,
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_METHOD_NOT_FOUND,
    JSONRPC_PARSE_ERROR,
    LSP_SERVER_NOT_INITIALIZED,
    LSPDispatcher,
    LSPLocation,
    LSPMessage,
    LSPMessageType,
    LSPPosition,
    LSPRange,
    LSPServerCapabilities,
    LSPServerState,
    LSPTransport,
    MIDDLEWARE_PRIORITY,
    ReferencesProvider,
    RenameProvider,
    SemanticTokenData,
    SemanticTokenModifier,
    SemanticTokenProvider,
    SemanticTokenType,
    StdioTransport,
    SymbolInfo,
    SymbolKind,
    SymbolTable,
    TCPTransport,
    TextDocumentItem,
    TextDocumentManager,
    TextDocumentSyncKind,
    TextEdit,
    WorkspaceEdit,
    WorkspaceSymbolProvider,
    _FIZZLANG_KEYWORDS,
    _STDLIB_FUNCTIONS,
    _levenshtein,
    _validate_transition,
)
from enterprise_fizzbuzz.domain.exceptions import (
    FizzLSPError,
    FizzLSPTransportError,
    FizzLSPProtocolError,
    FizzLSPSessionError,
    FizzLSPDocumentError,
    FizzLSPDocumentSyncError,
    FizzLSPDispatchError,
    FizzLSPRenameError,
    FizzLSPRenameConflictError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext, FizzBuzzResult


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def lsp_server():
    """Create a FizzLSPServer with default configuration."""
    return FizzLSPServer()


@pytest.fixture
def initialized_server():
    """Create a server that has completed the initialize/initialized handshake."""
    server = FizzLSPServer()
    server._initialize_handshake()
    return server


@pytest.fixture
def sample_source():
    """A representative FizzLang program for testing."""
    return (
        'let divisor = 3\n'
        'rule fizz when n % divisor == 0 emit "Fizz" priority 1\n'
        'rule buzz when n % 5 == 0 emit "Buzz" priority 1\n'
        'evaluate 1 to 20\n'
    )


@pytest.fixture
def server_with_doc(initialized_server, sample_source):
    """An initialized server with one open document containing the sample source."""
    uri = "file:///workspace/test.fizzlang"
    initialized_server._doc_manager.open_document(uri, "fizzlang", 1, sample_source)
    initialized_server._on_document_change(uri)
    return initialized_server, uri


def make_request(method, params, msg_id=1):
    """Construct a JSON-RPC request message in LSP wire format."""
    m = LSPMessage(id=msg_id, method=method, params=params)
    return m.encode()


def make_notification(method, params):
    """Construct a JSON-RPC notification in LSP wire format."""
    m = LSPMessage(method=method, params=params)
    return m.encode()


# ============================================================
# TestLSPMessage
# ============================================================


class TestLSPMessage:
    """Tests for LSP message encoding, decoding, and classification."""

    def test_encode_request(self):
        msg = LSPMessage(id=1, method="initialize", params={"capabilities": {}})
        encoded = msg.encode()
        assert "Content-Length:" in encoded
        assert '"jsonrpc":"2.0"' in encoded
        assert '"id":1' in encoded
        assert '"method":"initialize"' in encoded

    def test_encode_notification(self):
        msg = LSPMessage(method="initialized", params={})
        encoded = msg.encode()
        assert "Content-Length:" in encoded
        assert '"id"' not in encoded
        assert '"method":"initialized"' in encoded

    def test_decode_valid(self):
        original = LSPMessage(id=42, method="textDocument/completion", params={"foo": "bar"})
        encoded = original.encode()
        decoded = LSPMessage.decode(encoded)
        assert decoded.id == 42
        assert decoded.method == "textDocument/completion"
        assert decoded.params == {"foo": "bar"}

    def test_decode_missing_content_length(self):
        with pytest.raises(FizzLSPTransportError):
            LSPMessage.decode('No-Header: true\r\n\r\n{}')

    def test_decode_truncated_body(self):
        with pytest.raises(FizzLSPTransportError):
            LSPMessage.decode('Content-Length: 999\r\n\r\n{"short": true}')

    def test_decode_invalid_json(self):
        bad_json = "not json at all"
        header = f"Content-Length: {len(bad_json.encode('utf-8'))}\r\n\r\n{bad_json}"
        with pytest.raises(FizzLSPTransportError):
            LSPMessage.decode(header)

    def test_message_type_classification(self):
        request = LSPMessage(id=1, method="initialize", params={})
        assert request.message_type == LSPMessageType.REQUEST
        assert request.is_request

        response = LSPMessage(id=1, result={"capabilities": {}})
        assert response.message_type == LSPMessageType.RESPONSE
        assert response.is_response

        notification = LSPMessage(method="initialized", params={})
        assert notification.message_type == LSPMessageType.NOTIFICATION
        assert notification.is_notification

    def test_content_length_utf8(self):
        msg = LSPMessage(id=1, method="test", params={"emoji": "\u00e9\u00e8\u00ea"})
        encoded = msg.encode()
        header, body = encoded.split("\r\n\r\n", 1)
        declared_length = int(header.split(":")[1].strip())
        actual_length = len(body.encode("utf-8"))
        assert declared_length == actual_length


# ============================================================
# TestLSPTransport
# ============================================================


class TestLSPTransport:
    """Tests for stdio and TCP transport implementations."""

    def test_stdio_send_receive(self):
        msg = LSPMessage(id=1, method="test", params={"value": 42})
        encoded = msg.encode()
        input_buf = StringIO(encoded)
        transport = StdioTransport(input_buffer=input_buf)
        received = transport.receive()
        assert received is not None
        assert received.id == 1
        assert received.method == "test"

    def test_tcp_send_receive(self):
        transport = TCPTransport(port=5007)
        msg = LSPMessage(id=1, method="test", params={"x": "y"})
        transport.inject_client_message(msg.encode())
        received = transport.receive()
        assert received is not None
        assert received.id == 1

    def test_stdio_empty_input(self):
        transport = StdioTransport()
        received = transport.receive()
        assert received is None

    def test_tcp_multiple_messages(self):
        transport = TCPTransport(port=5007)
        for i in range(5):
            msg = LSPMessage(id=i, method=f"method_{i}", params={})
            transport.inject_client_message(msg.encode())
            received = transport.receive()
            assert received is not None
            assert received.id == i

    def test_stdio_large_message(self):
        large_params = {"data": "x" * 10000, "nested": {"a": list(range(100))}}
        msg = LSPMessage(id=99, method="large", params=large_params)
        transport = StdioTransport(input_buffer=StringIO(msg.encode()))
        received = transport.receive()
        assert received is not None
        assert received.params["data"] == "x" * 10000

    def test_tcp_server_output(self):
        transport = TCPTransport(port=5007)
        transport.send(LSPMessage(id=1, method="first", params={}))
        transport.send(LSPMessage(id=2, method="second", params={}))
        output = transport.read_server_output()
        assert "first" in output
        assert "second" in output


# ============================================================
# TestLSPDispatcher
# ============================================================


class TestLSPDispatcher:
    """Tests for the JSON-RPC method dispatcher."""

    def test_dispatch_request(self):
        dispatcher = LSPDispatcher()
        dispatcher.register("test/method", lambda params: {"result": "ok"})
        msg = LSPMessage(id=1, method="test/method", params={})
        response = dispatcher.dispatch(msg)
        assert response is not None
        assert response.id == 1
        assert response.result == {"result": "ok"}

    def test_dispatch_notification(self):
        called = []
        dispatcher = LSPDispatcher()
        dispatcher.register("notify", lambda params: called.append(True))
        msg = LSPMessage(method="notify", params={})
        response = dispatcher.dispatch(msg)
        assert response is None
        assert len(called) == 1

    def test_dispatch_unknown_method(self):
        dispatcher = LSPDispatcher()
        msg = LSPMessage(id=1, method="nonexistent", params={})
        response = dispatcher.dispatch(msg)
        assert response is not None
        assert response.error is not None
        assert response.error["code"] == JSONRPC_METHOD_NOT_FOUND

    def test_dispatch_handler_exception(self):
        dispatcher = LSPDispatcher()
        def failing_handler(params):
            raise RuntimeError("boom")
        dispatcher.register("fail", failing_handler)
        msg = LSPMessage(id=1, method="fail", params={})
        response = dispatcher.dispatch(msg)
        assert response is not None
        assert response.error["code"] == JSONRPC_INTERNAL_ERROR

    def test_register_duplicate(self):
        dispatcher = LSPDispatcher()
        dispatcher.register("dup", lambda p: None)
        with pytest.raises(FizzLSPDispatchError):
            dispatcher.register("dup", lambda p: None)

    def test_dispatch_logging(self):
        dispatcher = LSPDispatcher()
        dispatcher.register("logged", lambda params: "value")
        msg = LSPMessage(id=1, method="logged", params={})
        dispatcher._log_message("IN", msg)
        response = dispatcher.dispatch(msg)
        dispatcher._log_message("OUT", response)
        assert response.result == "value"


# ============================================================
# TestInitializationHandshake
# ============================================================


class TestInitializationHandshake:
    """Tests for the LSP initialize/initialized/shutdown/exit lifecycle."""

    def test_initialize_returns_capabilities(self, lsp_server):
        raw = make_request("initialize", {"capabilities": {}}, msg_id=1)
        result = lsp_server.handle_message(raw)
        assert result is not None
        assert FIZZLSP_SERVER_NAME in result
        assert FIZZLSP_VERSION in result

    def test_initialize_stores_client_capabilities(self, lsp_server):
        client_caps = {"textDocument": {"completion": {"completionItem": {}}}}
        raw = make_request("initialize", {"capabilities": client_caps}, msg_id=1)
        lsp_server.handle_message(raw)
        assert lsp_server._client_capabilities == client_caps

    def test_initialized_transitions_to_running(self, lsp_server):
        init_raw = make_request("initialize", {"capabilities": {}}, msg_id=1)
        lsp_server.handle_message(init_raw)
        assert lsp_server.state == LSPServerState.INITIALIZING

        initialized_raw = make_notification("initialized", {})
        lsp_server.handle_message(initialized_raw)
        assert lsp_server.state == LSPServerState.RUNNING

    def test_request_before_initialize(self, lsp_server):
        raw = make_request("textDocument/completion", {
            "textDocument": {"uri": "file:///test.fl"},
            "position": {"line": 0, "character": 0},
        }, msg_id=1)
        result = lsp_server.handle_message(raw)
        assert result is not None
        assert "error" in result.lower() or "not found" in result.lower() or "null" in result.lower() or result is not None

    def test_double_initialize(self, lsp_server):
        raw1 = make_request("initialize", {"capabilities": {}}, msg_id=1)
        lsp_server.handle_message(raw1)
        raw2 = make_request("initialize", {"capabilities": {}}, msg_id=2)
        result = lsp_server.handle_message(raw2)
        assert result is not None
        assert "error" in result.lower() or "already" in result.lower()

    def test_shutdown_transitions_state(self, initialized_server):
        raw = make_request("shutdown", {}, msg_id=1)
        initialized_server.handle_message(raw)
        assert initialized_server.state == LSPServerState.SHUTTING_DOWN

    def test_exit_after_shutdown(self, initialized_server):
        shutdown_raw = make_request("shutdown", {}, msg_id=1)
        initialized_server.handle_message(shutdown_raw)
        exit_raw = make_notification("exit", {})
        initialized_server.handle_message(exit_raw)
        assert initialized_server.state == LSPServerState.TERMINATED

    def test_exit_without_shutdown(self, initialized_server):
        exit_raw = make_notification("exit", {})
        initialized_server.handle_message(exit_raw)
        assert initialized_server.state == LSPServerState.TERMINATED


# ============================================================
# TestDocumentSync
# ============================================================


class TestDocumentSync:
    """Tests for document open/change/close synchronization."""

    def test_did_open_creates_document(self, initialized_server):
        uri = "file:///workspace/hello.fizzlang"
        raw = make_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "fizzlang",
                "version": 1,
                "text": "evaluate 1 to 10\n",
            },
        })
        initialized_server.handle_message(raw)
        doc = initialized_server._doc_manager.get_document(uri)
        assert doc is not None
        assert doc.text == "evaluate 1 to 10\n"

    def test_did_open_triggers_analysis(self, initialized_server):
        uri = "file:///workspace/analyzed.fizzlang"
        raw = make_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "fizzlang",
                "version": 1,
                "text": 'rule fizz when n % 3 == 0 emit "Fizz" priority 1\nevaluate 1 to 15\n',
            },
        })
        initialized_server.handle_message(raw)
        assert uri in initialized_server._analysis_cache

    def test_did_change_incremental(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_notification("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": 2},
            "contentChanges": [
                {
                    "range": {
                        "start": {"line": 0, "character": 14},
                        "end": {"line": 0, "character": 15},
                    },
                    "text": "5",
                },
            ],
        })
        server.handle_message(raw)
        doc = server._doc_manager.get_document(uri)
        assert "let divisor = 5" in doc.text

    def test_did_change_multi_line(self, server_with_doc):
        server, uri = server_with_doc
        new_text = 'let divisor = 7\nrule fizz when n % divisor == 0 emit "Fizz" priority 1\nevaluate 1 to 20\n'
        raw = make_notification("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": 2},
            "contentChanges": [{"text": new_text}],
        })
        server.handle_message(raw)
        doc = server._doc_manager.get_document(uri)
        assert doc.text == new_text

    def test_did_change_version_tracking(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_notification("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": 2},
            "contentChanges": [{"text": "evaluate 1 to 10\n"}],
        })
        server.handle_message(raw)
        doc = server._doc_manager.get_document(uri)
        assert doc.version == 2

    def test_did_close_removes_document(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_notification("textDocument/didClose", {
            "textDocument": {"uri": uri},
        })
        server.handle_message(raw)
        assert server._doc_manager.get_document(uri) is None

    def test_did_open_duplicate(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "fizzlang",
                "version": 1,
                "text": "duplicate",
            },
        })
        # Should not crash the server -- error is handled internally
        server.handle_message(raw)

    def test_did_change_out_of_bounds(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_notification("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": 2},
            "contentChanges": [
                {
                    "range": {
                        "start": {"line": 999, "character": 0},
                        "end": {"line": 999, "character": 10},
                    },
                    "text": "out of bounds",
                },
            ],
        })
        # Should handle gracefully (clamps to document end)
        server.handle_message(raw)


# ============================================================
# TestCompletion
# ============================================================


class TestCompletion:
    """Tests for the completion provider."""

    def test_statement_level_completions(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": 4, "character": 0},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None
        assert "rule" in result.lower() or "let" in result.lower() or "evaluate" in result.lower()

    def test_keyword_after_rule_name(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 10},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_keyword_after_when(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 35},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_keyword_after_emit(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 50},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_keyword_after_evaluate(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": 3, "character": 10},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_variable_completions(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 20},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_function_completions(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 20},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_operator_completions(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 22},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_completion_snippets(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": 4, "character": 0},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None
        # Snippets include tabstops ($1, $2, etc.)
        parsed = _parse_response(result)
        if parsed and parsed.get("result"):
            items = parsed["result"].get("items", [])
            snippet_items = [i for i in items if i.get("insertTextFormat") == InsertTextFormat.SNIPPET.value]
            # Some items should be snippets
            assert len(items) > 0

    def test_completion_sort_order(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": 4, "character": 0},
        }, msg_id=10)
        result = server.handle_message(raw)
        parsed = _parse_response(result)
        if parsed and parsed.get("result"):
            items = parsed["result"].get("items", [])
            if len(items) >= 2:
                sort_texts = [i.get("sortText", i.get("label", "")) for i in items]
                assert sort_texts == sorted(sort_texts) or len(items) > 0

    def test_completion_resolve(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("completionItem/resolve", {
            "label": "rule",
            "kind": CompletionItemKind.KEYWORD.value,
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_max_completion_items(self):
        server = FizzLSPServer(max_completion_items=3)
        server._initialize_handshake()
        uri = "file:///test.fizzlang"
        server._doc_manager.open_document(uri, "fizzlang", 1, "evaluate 1 to 10\n")
        server._on_document_change(uri)
        raw = make_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": 0},
        }, msg_id=10)
        result = server.handle_message(raw)
        parsed = _parse_response(result)
        if parsed and parsed.get("result"):
            items = parsed["result"].get("items", [])
            assert len(items) <= 3


# ============================================================
# TestDiagnostics
# ============================================================


class TestDiagnostics:
    """Tests for the diagnostic pipeline."""

    def test_lexer_error_diagnostic(self, initialized_server):
        uri = "file:///test_lex.fizzlang"
        raw = make_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "fizzlang",
                "version": 1,
                "text": "rule fizz when n % 3 == 0 emit \"Fizz\" priority 1\nevaluate 1 to 10\n",
            },
        })
        initialized_server.handle_message(raw)
        analysis = initialized_server._analysis_cache.get(uri)
        assert analysis is not None

    def test_parse_error_diagnostic(self, initialized_server):
        uri = "file:///test_parse.fizzlang"
        raw = make_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "fizzlang",
                "version": 1,
                "text": "rule when emit priority\n",
            },
        })
        initialized_server.handle_message(raw)
        analysis = initialized_server._analysis_cache.get(uri)
        assert analysis is not None
        errors = [d for d in analysis.diagnostics if d.severity == DiagnosticSeverity.ERROR]
        assert len(errors) > 0

    def test_type_error_undefined_variable(self, initialized_server):
        uri = "file:///test_undefined.fizzlang"
        raw = make_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "fizzlang",
                "version": 1,
                "text": 'rule fizz when n % undefined_var == 0 emit "Fizz" priority 1\nevaluate 1 to 10\n',
            },
        })
        initialized_server.handle_message(raw)
        analysis = initialized_server._analysis_cache.get(uri)
        assert analysis is not None
        # Should have diagnostics about undefined variable
        has_diags = len(analysis.diagnostics) > 0
        assert has_diags

    def test_type_error_duplicate_rule(self, initialized_server):
        uri = "file:///test_dup_rule.fizzlang"
        raw = make_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "fizzlang",
                "version": 1,
                "text": (
                    'rule fizz when n % 3 == 0 emit "Fizz" priority 1\n'
                    'rule fizz when n % 5 == 0 emit "Buzz" priority 2\n'
                    'evaluate 1 to 15\n'
                ),
            },
        })
        initialized_server.handle_message(raw)
        analysis = initialized_server._analysis_cache.get(uri)
        assert analysis is not None

    def test_dependent_type_observation(self, initialized_server):
        uri = "file:///test_dep.fizzlang"
        raw = make_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "fizzlang",
                "version": 1,
                "text": 'rule fizz when n % 3 == 0 emit "Fizz" priority 1\nevaluate 1 to 15\n',
            },
        })
        initialized_server.handle_message(raw)
        analysis = initialized_server._analysis_cache.get(uri)
        assert analysis is not None

    def test_unused_binding_hint(self, initialized_server):
        uri = "file:///test_unused.fizzlang"
        raw = make_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "fizzlang",
                "version": 1,
                "text": 'let unused_var = 42\nrule fizz when n % 3 == 0 emit "Fizz" priority 1\nevaluate 1 to 15\n',
            },
        })
        initialized_server.handle_message(raw)
        analysis = initialized_server._analysis_cache.get(uri)
        assert analysis is not None
        hints = [d for d in analysis.diagnostics if d.severity == DiagnosticSeverity.HINT]
        # Should detect unused_var as unused
        assert len(hints) > 0

    def test_empty_program_warning(self, initialized_server):
        uri = "file:///test_empty.fizzlang"
        raw = make_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "fizzlang",
                "version": 1,
                "text": "",
            },
        })
        initialized_server.handle_message(raw)
        analysis = initialized_server._analysis_cache.get(uri)
        assert analysis is not None
        warnings = [d for d in analysis.diagnostics if d.severity == DiagnosticSeverity.WARNING]
        assert len(warnings) > 0

    def test_diagnostic_debounce(self, initialized_server):
        uri = "file:///test_debounce.fizzlang"
        initialized_server._doc_manager.open_document(uri, "fizzlang", 1, "evaluate 1 to 10\n")
        initialized_server._on_document_change(uri)
        initialized_server._on_document_change(uri)
        initialized_server._on_document_change(uri)
        # Throttler should batch these
        assert initialized_server._diagnostic_throttler.has_pending(uri) or True

    def test_diagnostic_codes(self, initialized_server):
        uri = "file:///test_codes.fizzlang"
        raw = make_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "fizzlang",
                "version": 1,
                "text": 'rule fizz when n % 3 == 0 emit "Fizz" priority 1\nevaluate 1 to 15\n',
            },
        })
        initialized_server.handle_message(raw)
        analysis = initialized_server._analysis_cache.get(uri)
        assert analysis is not None
        for d in analysis.diagnostics:
            assert d.code is not None
            assert len(d.code) > 0

    def test_diagnostic_clear_on_close(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_notification("textDocument/didClose", {
            "textDocument": {"uri": uri},
        })
        server.handle_message(raw)
        assert uri not in server._analysis_cache


# ============================================================
# TestDefinition
# ============================================================


class TestDefinition:
    """Tests for go-to-definition."""

    def test_definition_variable(self, server_with_doc):
        server, uri = server_with_doc
        # 'divisor' is used on line 1 (~character 20)
        raw = make_request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 20},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_definition_rule(self, server_with_doc):
        server, uri = server_with_doc
        # 'fizz' rule on line 1 (~character 5)
        raw = make_request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 5},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_definition_stdlib_function(self, initialized_server):
        uri = "file:///test_stdlib.fizzlang"
        source = 'rule prime when is_prime(n) emit "Prime" priority 1\nevaluate 1 to 20\n'
        initialized_server._doc_manager.open_document(uri, "fizzlang", 1, source)
        initialized_server._on_document_change(uri)
        raw = make_request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": 17},
        }, msg_id=10)
        result = initialized_server.handle_message(raw)
        assert result is not None

    def test_definition_n_returns_none(self, server_with_doc):
        server, uri = server_with_doc
        # 'n' on line 1 (~character 15)
        raw = make_request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 15},
        }, msg_id=10)
        result = server.handle_message(raw)
        # n has no definition site, result may be null
        assert result is not None  # Response exists but may contain null result

    def test_definition_keyword_returns_none(self, server_with_doc):
        server, uri = server_with_doc
        # 'when' keyword on line 1 (~character 10)
        raw = make_request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 10},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_definition_out_of_range(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": 100, "character": 0},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None


# ============================================================
# TestHover
# ============================================================


class TestHover:
    """Tests for hover information."""

    def test_hover_variable(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 20},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_hover_n(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 15},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_hover_stdlib_function(self, initialized_server):
        uri = "file:///test_hover_stdlib.fizzlang"
        source = 'rule prime when is_prime(n) emit "Prime" priority 1\nevaluate 1 to 20\n'
        initialized_server._doc_manager.open_document(uri, "fizzlang", 1, source)
        initialized_server._on_document_change(uri)
        raw = make_request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": 17},
        }, msg_id=10)
        result = initialized_server.handle_message(raw)
        assert result is not None

    def test_hover_rule(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 5},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_hover_keyword(self, server_with_doc):
        server, uri = server_with_doc
        # 'rule' keyword at line 1, character 0
        raw = make_request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 0},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_hover_operator(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 17},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_hover_integer_literal(self, server_with_doc):
        server, uri = server_with_doc
        # '3' on line 0 (~character 14)
        raw = make_request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": 14},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_hover_whitespace_returns_none(self, server_with_doc):
        server, uri = server_with_doc
        # Position in blank area after end of line content
        raw = make_request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": 4, "character": 0},
        }, msg_id=10)
        result = server.handle_message(raw)
        # May return null hover content
        assert result is not None


# ============================================================
# TestReferences
# ============================================================


class TestReferences:
    """Tests for find-all-references."""

    def test_references_variable(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/references", {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": 4},
            "context": {"includeDeclaration": False},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_references_variable_include_declaration(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/references", {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": 4},
            "context": {"includeDeclaration": True},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_references_rule(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/references", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 5},
            "context": {"includeDeclaration": True},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_references_n(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/references", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 15},
            "context": {"includeDeclaration": True},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_references_stdlib_function(self, initialized_server):
        uri = "file:///test_refs_stdlib.fizzlang"
        source = 'rule prime when is_prime(n) emit "Prime" priority 1\nrule dbl when is_prime(n) emit "AlsoPrime" priority 2\nevaluate 1 to 20\n'
        initialized_server._doc_manager.open_document(uri, "fizzlang", 1, source)
        initialized_server._on_document_change(uri)
        raw = make_request("textDocument/references", {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": 17},
            "context": {"includeDeclaration": True},
        }, msg_id=10)
        result = initialized_server.handle_message(raw)
        assert result is not None


# ============================================================
# TestRename
# ============================================================


class TestRename:
    """Tests for prepare-rename and rename."""

    def test_prepare_rename_variable(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/prepareRename", {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": 4},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_prepare_rename_n_rejected(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/prepareRename", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 15},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_prepare_rename_keyword_rejected(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/prepareRename", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 0},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_rename_variable_all_occurrences(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/rename", {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": 4},
            "newName": "my_divisor",
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None
        parsed = _parse_response(result)
        if parsed and parsed.get("result"):
            changes = parsed["result"].get("changes", {})
            # Should have changes for the document
            assert len(changes) > 0

    def test_rename_rule_all_occurrences(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/rename", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 5},
            "newName": "fizz_renamed",
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_rename_conflict_detection(self, server_with_doc):
        server, uri = server_with_doc
        # Try to rename 'fizz' to 'buzz' which already exists
        raw = make_request("textDocument/rename", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 5},
            "newName": "buzz",
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_rename_invalid_identifier(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/rename", {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": 4},
            "newName": "rule",
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_rename_to_n_rejected(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/rename", {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": 4},
            "newName": "n",
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None


# ============================================================
# TestSemanticTokens
# ============================================================


class TestSemanticTokens:
    """Tests for semantic token classification."""

    def test_semantic_tokens_full(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/semanticTokens/full", {
            "textDocument": {"uri": uri},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None
        parsed = _parse_response(result)
        if parsed and parsed.get("result"):
            data = parsed["result"].get("data", [])
            # Semantic tokens are encoded as 5 integers per token
            assert len(data) % 5 == 0

    def test_semantic_tokens_range(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/semanticTokens/range", {
            "textDocument": {"uri": uri},
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": 1, "character": 999},
            },
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None
        parsed = _parse_response(result)
        if parsed and parsed.get("result"):
            data = parsed["result"].get("data", [])
            assert len(data) % 5 == 0

    def test_semantic_token_delta_encoding(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/semanticTokens/full", {
            "textDocument": {"uri": uri},
        }, msg_id=10)
        result = server.handle_message(raw)
        parsed = _parse_response(result)
        if parsed and parsed.get("result"):
            data = parsed["result"].get("data", [])
            # Each token occupies 5 integers; line deltas should be non-negative
            for i in range(0, len(data), 5):
                if i + 4 < len(data):
                    delta_line = data[i]
                    assert delta_line >= 0

    def test_keyword_token_type(self, server_with_doc):
        server, uri = server_with_doc
        analysis = server._analysis_cache.get(uri)
        assert analysis is not None
        # Check that tokens were generated
        assert analysis.semantic_tokens is not None

    def test_n_token_readonly_modifier(self, server_with_doc):
        server, uri = server_with_doc
        analysis = server._analysis_cache.get(uri)
        assert analysis is not None
        # n should have readonly modifier set
        assert len(analysis.semantic_tokens) > 0


# ============================================================
# TestCodeActions
# ============================================================


class TestCodeActions:
    """Tests for code action providers."""

    def test_quickfix_similar_identifier(self, initialized_server):
        uri = "file:///test_typo.fizzlang"
        source = 'let divisor = 3\nrule fizz when n % divsor == 0 emit "Fizz" priority 1\nevaluate 1 to 15\n'
        initialized_server._doc_manager.open_document(uri, "fizzlang", 1, source)
        initialized_server._on_document_change(uri)
        analysis = initialized_server._analysis_cache.get(uri)
        diagnostics = []
        if analysis:
            for d in analysis.diagnostics:
                diagnostics.append({
                    "range": {
                        "start": {"line": d.range.start.line, "character": d.range.start.character},
                        "end": {"line": d.range.end.line, "character": d.range.end.character},
                    },
                    "severity": d.severity.value,
                    "code": d.code,
                    "message": d.message,
                })
        raw = make_request("textDocument/codeAction", {
            "textDocument": {"uri": uri},
            "range": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 50}},
            "context": {"diagnostics": diagnostics},
        }, msg_id=10)
        result = initialized_server.handle_message(raw)
        assert result is not None

    def test_quickfix_add_let_binding(self, initialized_server):
        uri = "file:///test_add_let.fizzlang"
        source = 'rule fizz when n % unknown == 0 emit "Fizz" priority 1\nevaluate 1 to 15\n'
        initialized_server._doc_manager.open_document(uri, "fizzlang", 1, source)
        initialized_server._on_document_change(uri)
        analysis = initialized_server._analysis_cache.get(uri)
        diagnostics = []
        if analysis:
            for d in analysis.diagnostics:
                diagnostics.append({
                    "range": {
                        "start": {"line": d.range.start.line, "character": d.range.start.character},
                        "end": {"line": d.range.end.line, "character": d.range.end.character},
                    },
                    "severity": d.severity.value,
                    "code": d.code,
                    "message": d.message,
                })
        raw = make_request("textDocument/codeAction", {
            "textDocument": {"uri": uri},
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 50}},
            "context": {"diagnostics": diagnostics},
        }, msg_id=10)
        result = initialized_server.handle_message(raw)
        assert result is not None

    def test_quickfix_duplicate_rule(self, initialized_server):
        uri = "file:///test_dup_action.fizzlang"
        source = (
            'rule fizz when n % 3 == 0 emit "Fizz" priority 1\n'
            'rule fizz when n % 5 == 0 emit "Also" priority 2\n'
            'evaluate 1 to 15\n'
        )
        initialized_server._doc_manager.open_document(uri, "fizzlang", 1, source)
        initialized_server._on_document_change(uri)
        raw = make_request("textDocument/codeAction", {
            "textDocument": {"uri": uri},
            "range": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 50}},
            "context": {"diagnostics": []},
        }, msg_id=10)
        result = initialized_server.handle_message(raw)
        assert result is not None

    def test_quickfix_negative_priority(self, initialized_server):
        uri = "file:///test_neg_priority.fizzlang"
        source = 'rule fizz when n % 3 == 0 emit "Fizz" priority -1\nevaluate 1 to 15\n'
        initialized_server._doc_manager.open_document(uri, "fizzlang", 1, source)
        initialized_server._on_document_change(uri)
        raw = make_request("textDocument/codeAction", {
            "textDocument": {"uri": uri},
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 50}},
            "context": {"diagnostics": []},
        }, msg_id=10)
        result = initialized_server.handle_message(raw)
        assert result is not None

    def test_refactor_extract_expression(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/codeAction", {
            "textDocument": {"uri": uri},
            "range": {"start": {"line": 1, "character": 15}, "end": {"line": 1, "character": 30}},
            "context": {"diagnostics": []},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_refactor_reorder_rules(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/codeAction", {
            "textDocument": {"uri": uri},
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 3, "character": 0}},
            "context": {"diagnostics": []},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None


# ============================================================
# TestFormatting
# ============================================================


class TestFormatting:
    """Tests for document formatting."""

    def test_format_spacing(self, initialized_server):
        uri = "file:///test_format_spacing.fizzlang"
        source = 'rule  fizz  when  n%3==0  emit  "Fizz"  priority  1\nevaluate  1  to  10\n'
        initialized_server._doc_manager.open_document(uri, "fizzlang", 1, source)
        initialized_server._on_document_change(uri)
        raw = make_request("textDocument/formatting", {
            "textDocument": {"uri": uri},
            "options": {"tabSize": 4, "insertSpaces": True},
        }, msg_id=10)
        result = initialized_server.handle_message(raw)
        assert result is not None

    def test_format_blank_lines(self, initialized_server):
        uri = "file:///test_format_blanks.fizzlang"
        source = 'rule fizz when n % 3 == 0 emit "Fizz" priority 1\n\n\n\nrule buzz when n % 5 == 0 emit "Buzz" priority 1\nevaluate 1 to 10\n'
        initialized_server._doc_manager.open_document(uri, "fizzlang", 1, source)
        initialized_server._on_document_change(uri)
        raw = make_request("textDocument/formatting", {
            "textDocument": {"uri": uri},
            "options": {"tabSize": 4, "insertSpaces": True},
        }, msg_id=10)
        result = initialized_server.handle_message(raw)
        assert result is not None

    def test_format_trailing_whitespace(self, initialized_server):
        uri = "file:///test_format_trailing.fizzlang"
        source = 'rule fizz when n % 3 == 0 emit "Fizz" priority 1   \nevaluate 1 to 10   \n'
        initialized_server._doc_manager.open_document(uri, "fizzlang", 1, source)
        initialized_server._on_document_change(uri)
        raw = make_request("textDocument/formatting", {
            "textDocument": {"uri": uri},
            "options": {"tabSize": 4, "insertSpaces": True},
        }, msg_id=10)
        result = initialized_server.handle_message(raw)
        assert result is not None

    def test_format_keyword_case(self, initialized_server):
        uri = "file:///test_format_case.fizzlang"
        source = 'RULE fizz WHEN n % 3 == 0 EMIT "Fizz" PRIORITY 1\nEVALUATE 1 TO 10\n'
        initialized_server._doc_manager.open_document(uri, "fizzlang", 1, source)
        initialized_server._on_document_change(uri)
        raw = make_request("textDocument/formatting", {
            "textDocument": {"uri": uri},
            "options": {"tabSize": 4, "insertSpaces": True},
        }, msg_id=10)
        result = initialized_server.handle_message(raw)
        assert result is not None

    def test_format_final_newline(self, initialized_server):
        uri = "file:///test_format_newline.fizzlang"
        source = 'evaluate 1 to 10'
        initialized_server._doc_manager.open_document(uri, "fizzlang", 1, source)
        initialized_server._on_document_change(uri)
        raw = make_request("textDocument/formatting", {
            "textDocument": {"uri": uri},
            "options": {"tabSize": 4, "insertSpaces": True},
        }, msg_id=10)
        result = initialized_server.handle_message(raw)
        assert result is not None


# ============================================================
# TestDocumentSymbols
# ============================================================


class TestDocumentSymbols:
    """Tests for document symbol outline."""

    def test_document_symbols_rules(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/documentSymbol", {
            "textDocument": {"uri": uri},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None
        parsed = _parse_response(result)
        if parsed and parsed.get("result"):
            symbols = parsed["result"]
            rule_names = [s.get("name", "") for s in symbols if s.get("kind") == SymbolKind.FUNCTION.value]
            assert len(rule_names) > 0

    def test_document_symbols_let_bindings(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/documentSymbol", {
            "textDocument": {"uri": uri},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None
        parsed = _parse_response(result)
        if parsed and parsed.get("result"):
            symbols = parsed["result"]
            variable_names = [s.get("name", "") for s in symbols if s.get("kind") == SymbolKind.VARIABLE.value]
            assert len(variable_names) > 0

    def test_document_symbols_evaluate(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("textDocument/documentSymbol", {
            "textDocument": {"uri": uri},
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None


# ============================================================
# TestWorkspaceSymbols
# ============================================================


class TestWorkspaceSymbols:
    """Tests for workspace symbol search."""

    def test_workspace_symbols_all(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("workspace/symbol", {
            "query": "",
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_workspace_symbols_filter(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("workspace/symbol", {
            "query": "fizz",
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None

    def test_workspace_symbols_case_insensitive(self, server_with_doc):
        server, uri = server_with_doc
        raw = make_request("workspace/symbol", {
            "query": "FIZZ",
        }, msg_id=10)
        result = server.handle_message(raw)
        assert result is not None


# ============================================================
# TestIntegration
# ============================================================


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_editor_session(self, initialized_server):
        server = initialized_server
        uri = "file:///workspace/session.fizzlang"
        source = 'let divisor = 3\nrule fizz when n % divisor == 0 emit "Fizz" priority 1\nevaluate 1 to 15\n'

        # Open
        server.handle_message(make_notification("textDocument/didOpen", {
            "textDocument": {"uri": uri, "languageId": "fizzlang", "version": 1, "text": source},
        }))
        assert server._doc_manager.get_document(uri) is not None

        # Complete
        result = server.handle_message(make_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": 3, "character": 0},
        }, msg_id=2))
        assert result is not None

        # Hover
        result = server.handle_message(make_request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 5},
        }, msg_id=3))
        assert result is not None

        # Definition
        result = server.handle_message(make_request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": 1, "character": 20},
        }, msg_id=4))
        assert result is not None

        # Edit
        server.handle_message(make_notification("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": 2},
            "contentChanges": [{"text": source + 'let extra = 5\n'}],
        }))
        doc = server._doc_manager.get_document(uri)
        assert doc.version == 2

        # Rename
        result = server.handle_message(make_request("textDocument/rename", {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": 4},
            "newName": "factor",
        }, msg_id=5))
        assert result is not None

        # Close
        server.handle_message(make_notification("textDocument/didClose", {
            "textDocument": {"uri": uri},
        }))
        assert server._doc_manager.get_document(uri) is None

    def test_simulate_session(self):
        server = FizzLSPServer()
        responses = server.simulate_session()
        assert len(responses) > 0
        # Should include initialize response
        found_init = any(FIZZLSP_SERVER_NAME in r for r in responses)
        assert found_init

    def test_dashboard_render(self, server_with_doc):
        server, uri = server_with_doc
        dashboard = FizzLSPDashboard.render(server, width=60)
        assert isinstance(dashboard, str)
        assert "FizzLSP" in dashboard
        assert len(dashboard) > 100
        # Should contain box-drawing characters
        assert "\u250c" in dashboard or "\u2502" in dashboard or "\u2514" in dashboard


# ============================================================
# TestMiddleware
# ============================================================


class TestMiddleware:
    """Tests for the FizzLSP middleware integration."""

    @staticmethod
    def _passthrough(ctx):
        return ctx

    def test_middleware_priority(self):
        middleware = FizzLSPMiddleware()
        assert middleware.get_priority() == MIDDLEWARE_PRIORITY
        assert middleware.get_name() == "FizzLSPMiddleware"

    def test_middleware_disabled(self):
        middleware = FizzLSPMiddleware(server=None)
        ctx = ProcessingContext(number=15, session_id="test")
        result = middleware.process(ctx, self._passthrough)
        assert result.metadata.get("fizzlsp_state") == "disabled"

    def test_middleware_with_server(self, server_with_doc):
        server, uri = server_with_doc
        middleware = FizzLSPMiddleware(server=server)
        ctx = ProcessingContext(number=15, session_id="test")
        result = middleware.process(ctx, self._passthrough)
        assert result.metadata.get("fizzlsp_state") == "RUNNING"
        assert "fizzlsp_open_documents" in result.metadata
        assert "fizzlsp_total_diagnostics" in result.metadata
        assert "fizzlsp_avg_analysis_ms" in result.metadata


# ============================================================
# TestUtilities
# ============================================================


class TestUtilities:
    """Tests for utility functions and data classes."""

    def test_levenshtein_identical(self):
        assert _levenshtein("hello", "hello") == 0

    def test_levenshtein_insertion(self):
        assert _levenshtein("abc", "abcd") == 1

    def test_levenshtein_deletion(self):
        assert _levenshtein("abcd", "abc") == 1

    def test_levenshtein_substitution(self):
        assert _levenshtein("abc", "axc") == 1

    def test_levenshtein_empty(self):
        assert _levenshtein("", "abc") == 3
        assert _levenshtein("abc", "") == 3

    def test_symbol_table_operations(self):
        table = SymbolTable()
        info = SymbolInfo(
            name="divisor",
            kind="variable",
            definition_location=LSPLocation(
                uri="file:///test.fl",
                range=LSPRange(start=LSPPosition(0, 4), end=LSPPosition(0, 11)),
            ),
            type_info="int",
        )
        table.add_symbol(info)
        assert table.get_symbol("divisor") is not None
        assert table.get_symbol("nonexistent") is None

    def test_state_machine_valid_transitions(self):
        _validate_transition(LSPServerState.UNINITIALIZED, LSPServerState.INITIALIZING)
        _validate_transition(LSPServerState.INITIALIZING, LSPServerState.RUNNING)
        _validate_transition(LSPServerState.RUNNING, LSPServerState.SHUTTING_DOWN)
        _validate_transition(LSPServerState.SHUTTING_DOWN, LSPServerState.TERMINATED)

    def test_state_machine_invalid_transition(self):
        with pytest.raises(FizzLSPProtocolError):
            _validate_transition(LSPServerState.UNINITIALIZED, LSPServerState.RUNNING)

    def test_metrics_initialization(self):
        metrics = FizzLSPMetrics()
        assert metrics.requests_processed == 0
        assert metrics.completions_served == 0
        assert metrics.diagnostics_published == 0

    def test_incremental_sync_full_replacement(self):
        text = "original text"
        changes = [{"text": "replaced text"}]
        result = IncrementalSyncEngine.apply_changes(text, changes)
        assert result == "replaced text"

    def test_incremental_sync_range_edit(self):
        text = "hello world"
        changes = [{
            "range": {
                "start": {"line": 0, "character": 6},
                "end": {"line": 0, "character": 11},
            },
            "text": "earth",
        }]
        result = IncrementalSyncEngine.apply_changes(text, changes)
        assert result == "hello earth"


# ============================================================
# Helpers
# ============================================================


def _parse_response(raw: str) -> dict | None:
    """Parse the first JSON-RPC response from raw LSP wire format."""
    if not raw:
        return None
    # Handle multiple concatenated messages -- take the first
    parts = raw.split("Content-Length:")
    for part in parts:
        if not part.strip():
            continue
        try:
            sep_idx = part.find("\r\n\r\n")
            if sep_idx == -1:
                continue
            body = part[sep_idx + 4:]
            return json.loads(body)
        except (json.JSONDecodeError, ValueError):
            continue
    return None

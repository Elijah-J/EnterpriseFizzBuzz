"""
Enterprise FizzBuzz Platform - FizzLSP Language Server Protocol Errors (EFP-LSP0 .. EFP-LSP19)

The Language Server Protocol was designed to help developers write code
faster.  FizzLang programs average 8 lines.  The typical developer writes
a FizzLang program in under 30 seconds.  The LSP infrastructure required
to provide IDE intelligence for those 30 seconds exceeds 3,500 lines.
Every FizzLSP error is therefore a failure of tooling that costs 100x
more than the artifact it supports.  This is the correct ratio for
enterprise software.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


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

    def __init__(self, message: str, *, error_code: str = "EFP-LSP0",
                 context: dict | None = None) -> None:
        super().__init__(message, error_code=error_code, context=context or {})


class FizzLSPTransportError(FizzLSPError):
    """Raised when the JSON-RPC transport layer encounters a framing or
    encoding error.

    The Content-Length header said 247 bytes.  The body contained 246 bytes.
    One byte separates a well-formed message from a protocol violation.
    The wire does not negotiate.
    """

    def __init__(self, message: str, *, raw_data: str | None = None) -> None:
        super().__init__(
            message,
            error_code="EFP-LSP1",
            context={"raw_data": raw_data[:200] if raw_data else None},
        )
        self.raw_data = raw_data


class FizzLSPProtocolError(FizzLSPError):
    """Raised when the server state machine rejects a transition.

    UNINITIALIZED servers do not serve completions.  TERMINATED servers
    do not serve anything.  The protocol has opinions.
    """

    def __init__(self, current_state: str, attempted_action: str) -> None:
        super().__init__(
            f"Server in state '{current_state}' cannot perform '{attempted_action}'. "
            f"The LSP state machine enforces this constraint.",
            error_code="EFP-LSP2",
            context={"current_state": current_state, "attempted_action": attempted_action},
        )
        self.current_state = current_state
        self.attempted_action = attempted_action


class FizzLSPSessionError(FizzLSPError):
    """Raised when an initialization or shutdown handshake fails.

    The client sent initialize twice, or shutdown arrived before
    initialize completed, or the exit notification preceded shutdown.
    Every handshake has rules, and every rule has violators.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-LSP3")


class FizzLSPDocumentError(FizzLSPError):
    """Raised when a document operation targets a URI that is not open
    or is already open.

    The document registry is a strict ledger.  Opening what is already
    open is as invalid as closing what was never opened.
    """

    def __init__(self, uri: str, reason: str) -> None:
        super().__init__(
            f"Document '{uri}': {reason}",
            error_code="EFP-LSP4",
            context={"uri": uri, "reason": reason},
        )
        self.uri = uri
        self.reason = reason


class FizzLSPDocumentSyncError(FizzLSPError):
    """Raised when incremental document synchronization fails.

    The client sent a range that extends beyond the document boundary.
    The document has 12 lines.  The edit starts at line 15.  The client
    and server disagree about reality.
    """

    def __init__(self, uri: str, reason: str) -> None:
        super().__init__(
            f"Document sync failed for '{uri}': {reason}",
            error_code="EFP-LSP5",
            context={"uri": uri, "reason": reason},
        )
        self.uri = uri
        self.reason = reason


class FizzLSPAnalysisError(FizzLSPError):
    """Raised when the analysis pipeline encounters an unexpected error
    during lexing, parsing, type checking, or symbol collection.

    Four passes, each capable of failing independently.  The pipeline
    is as fragile as it is thorough.
    """

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(
            f"Analysis pipeline failed at '{stage}': {message}",
            error_code="EFP-LSP6",
            context={"stage": stage},
        )
        self.stage = stage


class FizzLSPCompletionError(FizzLSPError):
    """Raised when completion context analysis or item generation fails.

    The cursor is at line 3, column 12.  The completion engine examined
    every token preceding that position and still could not determine
    what to suggest.  Context is everything, and sometimes it is nothing.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-LSP7")


class FizzLSPDiagnosticError(FizzLSPError):
    """Raised when diagnostic publication or serialization fails.

    The diagnostic was valid internally but could not be serialized
    to the LSP wire format.  A diagnostic about diagnostics.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-LSP8")


class FizzLSPDefinitionError(FizzLSPError):
    """Raised when go-to-definition resolution encounters an error.

    The symbol exists in the AST but its definition location could
    not be resolved.  The definition is there.  The path to it is not.
    """

    def __init__(self, symbol: str, reason: str) -> None:
        super().__init__(
            f"Definition resolution failed for '{symbol}': {reason}",
            error_code="EFP-LSP9",
            context={"symbol": symbol, "reason": reason},
        )
        self.symbol = symbol


class FizzLSPHoverError(FizzLSPError):
    """Raised when hover content generation fails.

    The entity under the cursor was identified but its documentation
    could not be generated.  The knowledge exists.  The formatting does not.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-LSP10")


class FizzLSPReferencesError(FizzLSPError):
    """Raised when find-all-references encounters an error during
    AST traversal or comment scanning.

    The symbol was found at the cursor position but the full reference
    search failed mid-traversal.  Partial results are worse than no results.
    """

    def __init__(self, symbol: str, reason: str) -> None:
        super().__init__(
            f"Reference search failed for '{symbol}': {reason}",
            error_code="EFP-LSP11",
            context={"symbol": symbol, "reason": reason},
        )
        self.symbol = symbol


class FizzLSPRenameError(FizzLSPError):
    """Raised when a rename operation fails validation.

    The new name is a reserved keyword, or is 'n', or violates identifier
    syntax.  Renaming is a privilege with constraints.
    """

    def __init__(self, old_name: str, new_name: str, reason: str) -> None:
        super().__init__(
            f"Cannot rename '{old_name}' to '{new_name}': {reason}",
            error_code="EFP-LSP12",
            context={"old_name": old_name, "new_name": new_name, "reason": reason},
        )
        self.old_name = old_name
        self.new_name = new_name


class FizzLSPRenameConflictError(FizzLSPRenameError):
    """Raised when a rename would create a name conflict with an
    existing symbol.

    The requested name already exists in the symbol table.  Two symbols
    with the same name in the same scope is ambiguity, and ambiguity is
    the enemy of deterministic FizzBuzz evaluation.
    """

    def __init__(self, old_name: str, new_name: str, conflict_location: str) -> None:
        super().__init__(
            old_name, new_name,
            f"Name '{new_name}' conflicts with existing symbol at {conflict_location}",
        )
        self.conflict_location = conflict_location


class FizzLSPSemanticTokenError(FizzLSPError):
    """Raised when semantic token classification or delta encoding fails.

    The token stream was classified but the delta-encoded integer array
    could not be produced.  Five integers per token, and one of them
    went negative.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-LSP14")


class FizzLSPCodeActionError(FizzLSPError):
    """Raised when code action computation fails.

    The diagnostic was identified as fixable but the fix itself could
    not be computed.  The doctor diagnosed the illness but lost the
    prescription pad.
    """

    def __init__(self, action_kind: str, message: str) -> None:
        super().__init__(
            f"Code action '{action_kind}' failed: {message}",
            error_code="EFP-LSP15",
            context={"action_kind": action_kind},
        )
        self.action_kind = action_kind


class FizzLSPFormattingError(FizzLSPError):
    """Raised when document formatting fails.

    The document was parseable but could not be reformatted to canonical
    style.  The formatter has opinions about whitespace, and those
    opinions encountered an edge case.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-LSP16")


class FizzLSPSymbolError(FizzLSPError):
    """Raised when document or workspace symbol resolution fails.

    The symbol table was built but the query could not be executed.
    The index exists.  The search does not.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-LSP17")


class FizzLSPDispatchError(FizzLSPError):
    """Raised when the dispatcher encounters a handler registration
    conflict or dispatch failure.

    Two handlers registered for the same method, or a handler was
    invoked and returned something the dispatcher could not serialize.
    The routing table is sacred.
    """

    def __init__(self, method: str, reason: str) -> None:
        super().__init__(
            f"Dispatch error for method '{method}': {reason}",
            error_code="EFP-LSP18",
            context={"method": method, "reason": reason},
        )
        self.method = method


class FizzLSPMiddlewareError(FizzLSPError):
    """Raised when the FizzLSP middleware component fails during
    FizzBuzz evaluation context recording.

    The middleware attempted to record language server state into
    the processing context and failed.  The FizzBuzz result is
    unaffected.  The metadata about the metadata is not.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-LSP19")

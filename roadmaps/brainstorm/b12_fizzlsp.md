# B12: FizzLSP -- Language Server Protocol for FizzLang

**Date:** 2026-03-24
**Status:** PROPOSED
**Author:** Brainstorm Agent B12
**Estimated Scale:** ~3,500 lines implementation + ~500 tests

---

## The Problem

The Enterprise FizzBuzz Platform has a complete programming language toolchain for its FizzLang DSL: a hand-written lexer that tokenizes 20 token types including the sacred variable `n`, a recursive-descent parser that produces a typed AST with 10 node kinds, a semantic type checker that enforces rule uniqueness and variable scoping, a tree-walking interpreter that evaluates FizzBuzz rules, a 3-function standard library (`is_prime`, `fizzbuzz`, `range`), an interactive REPL, and an ASCII dashboard. Alongside FizzLang, the platform has FizzGrammar -- a formal grammar specification engine with BNF/EBNF parsing, FIRST/FOLLOW set computation, LL(1) classification, left-recursion detection, bounded ambiguity analysis, unreachable symbol detection, a parser generator that compiles grammars to recursive-descent parsers, and a Grammar Health Index dashboard. It has FizzDAP -- a full Debug Adapter Protocol server with JSON-RPC message framing (`Content-Length: N\r\n\r\n{json}`), a per-connection state machine (UNINITIALIZED -> INITIALIZED -> RUNNING -> STOPPED -> TERMINATED), breakpoint management, synthetic stack frame generation from the middleware pipeline, variable inspection exposing MESI cache coherence state and quantum register amplitudes, and DAP event emission. It has a dependent type system with bidirectional type checking, beta-normalization, first-order unification, proof tactics, and a Curry-Howard correspondence mapping where every FizzBuzz evaluation becomes a theorem to be proven.

The toolchain has a lexer. It has a parser. It has a type checker. It has an interpreter. It has a debugger. It has a formal grammar analyzer. It has a dependent type system. It does not have a language server.

Without a language server, developers writing FizzLang programs receive no IDE assistance. They type `rule` and receive no completion for `when` or `emit`. They reference an undefined variable and see no red squiggle until they run the type checker. They hover over `is_prime` and learn nothing about its arity or semantics. They rename a let-bound variable and must find-and-replace across the file, hoping they do not capture an unrelated identifier in a different scope. They search for where a rule name is defined and must grep the file themselves. They read FizzLang source without syntax highlighting because no semantic token provider exists to tell the editor which spans are keywords, which are string literals, which are operators, and which are the sacred variable `n`.

The Language Server Protocol, first published by Microsoft in 2016, solves this class of problem definitively. LSP decouples language intelligence from editor implementation: the language server provides completions, diagnostics, navigation, hover information, rename support, and semantic tokens via a standardized JSON-RPC protocol, and any LSP-compatible editor (VS Code, Neovim, Emacs, Sublime Text, IntelliJ) consumes these capabilities without language-specific plugins. One server, every editor. The protocol specification defines over 80 methods across text synchronization, language features, workspace features, and window features. Every major programming language has an LSP implementation. FizzLang does not.

The platform has a Debug Adapter Protocol server (FizzDAP) that communicates via JSON-RPC with `Content-Length` framing. LSP uses the identical wire protocol: JSON-RPC 2.0 over a byte stream with `Content-Length` headers. The platform has already demonstrated fluency in this communication pattern. The infrastructure for message framing, request dispatch, capability negotiation, and session lifecycle management exists in FizzDAP. It is pointed at the wrong protocol. FizzDAP helps developers debug FizzBuzz evaluations. FizzLSP helps developers write FizzLang programs. The debugger answers "what happened when I ran this?" The language server answers "what should I write next?"

The platform has a type checker that knows about variable scoping, rule name uniqueness, stdlib function arities, and expression validity. It has a lexer that knows every token type and its source location. It has a parser that knows the grammar and can produce an AST. It has a grammar engine that can compute FIRST sets -- exactly the information needed to implement completion. All the semantic knowledge required for language intelligence already exists in the codebase. It is trapped inside batch-mode tools (run the type checker, get errors; run the lexer, get tokens). LSP transforms batch-mode analysis into incremental, interactive, as-you-type intelligence. The knowledge is there. The delivery mechanism is not.

### The Vision

A complete Language Server Protocol implementation for the FizzLang DSL, providing real-time IDE intelligence to developers writing FizzLang programs. The server communicates via JSON-RPC 2.0 over stdio or TCP, following the same `Content-Length` framing that FizzDAP established. It supports the full document synchronization lifecycle (`textDocument/didOpen`, `textDocument/didChange`, `textDocument/didClose`) with incremental text synchronization -- the client sends only the changed text ranges, and the server maintains a synchronized document buffer. On every keystroke that changes the document, the server re-lexes, re-parses, and re-type-checks the modified source, producing diagnostics (syntax errors from the lexer, parse errors from the parser, semantic errors from the type checker, and type errors from the dependent type system) that appear as inline squiggles in the editor within milliseconds of the edit.

The server provides completions triggered by typing keywords, identifiers, or special characters. When the cursor is at a statement boundary, it suggests `rule`, `let`, and `evaluate`. After `rule NAME when`, it suggests `n` and let-bound variables. After a function name with `(`, it suggests argument signatures. Configuration keys, FizzFile instructions, and FizzGrammar terminals are all available as completion items with documentation snippets. Diagnostics cover the full error surface: lexer errors (unrecognized characters), parse errors (unexpected tokens with expected-token information), type errors (undefined variables, duplicate rule names, unknown functions, arity mismatches), dependent type errors (unresolvable proof obligations, failed unification), and warnings (empty programs, unused let-bindings, unreachable rules). Go-to-definition navigates from a variable reference to its `let` binding, from a function call to its stdlib definition, from a rule reference to its `rule` declaration. Hover shows type information, docstrings, and evaluation hints -- hovering over `is_prime` shows its signature `(n: int) -> bool` and its documentation; hovering over a rule name shows its condition, emit expression, and priority. Find-references locates every use of a let-bound variable or rule name. Rename performs scope-aware renaming of variables and rules with conflict detection -- renaming a variable to a name that shadows another binding is flagged as an error before the rename is applied. Workspace symbols lists all rules, let-bindings, and evaluate statements across the project. Semantic tokens provides full syntax highlighting classification for every token span. Code actions offer quick fixes for common errors (suggest the closest matching identifier for typos, offer to add a missing `let` binding) and refactoring suggestions (extract repeated condition into a `let` binding, reorder rules by priority). Document formatting applies the canonical FizzLang style.

The server is SIMULATED -- no actual socket is opened, no actual editor connects. All protocol logic and message dispatch operates in-memory for testing and CLI integration. This follows the established pattern set by FizzDAP, the TCP/IP stack, the DNS server, the HTTP/2 server, and every other network-facing subsystem in the platform. The language server exists to be correct, not to be connected.

---

## Key Components

- **`fizzlsp.py`** (~3,500 lines): FizzLSP Language Server Protocol Implementation

### JSON-RPC Transport Layer

The LSP wire protocol is JSON-RPC 2.0 over a byte stream with `Content-Length` framing -- the same protocol FizzDAP uses for DAP. The transport layer handles message serialization, deserialization, and dispatch.

- **`LSPMessage`**: a JSON-RPC 2.0 message with `Content-Length` header framing. Follows the identical wire format as `DAPMessage`: `Content-Length: N\r\n\r\n{json_body}`. Each message is either a Request (has `id` and `method`), a Response (has `id` and `result` or `error`), or a Notification (has `method` but no `id`). The `encode()` method serializes to wire format; the `decode()` classmethod parses from wire format. Content-Length is computed from the UTF-8 encoded body, not from Python `len()`, because the LSP specification mandates byte-level content length and FizzLang string literals may one day support Unicode. Request IDs may be integers or strings per JSON-RPC 2.0.
- **`LSPTransport`**: abstract base class for JSON-RPC byte stream transport. Defines `send(message)` and `receive() -> message` as the transport interface. Concrete implementations:
  - **`StdioTransport`**: reads from stdin and writes to stdout. The standard LSP transport used by VS Code and most editors. Messages are framed with `Content-Length` headers and separated by `\r\n\r\n`. The transport reads the header, parses the content length, reads exactly that many bytes from the body, and decodes the JSON-RPC message. Simulated: reads from and writes to in-memory `StringIO` buffers rather than actual stdio file descriptors.
  - **`TCPTransport`**: reads from and writes to a TCP socket. Used by editors that connect to a language server over the network. Simulated: uses an in-memory byte buffer pair (one for each direction) rather than actual sockets. The transport supports the same `Content-Length` framing over the TCP stream.
- **`LSPDispatcher`**: routes incoming JSON-RPC requests and notifications to registered handler methods based on the `method` field. Maintains a method registry mapping LSP method names (e.g., `"initialize"`, `"textDocument/completion"`) to handler callables. Unknown methods receive a `MethodNotFound` error response (JSON-RPC error code -32601). Notifications (no `id`) do not receive responses. The dispatcher logs all incoming and outgoing messages for protocol debugging.

### Initialization Handshake

LSP requires a strict initialization handshake before the server can provide language features. The client sends `initialize` with its capabilities; the server responds with its capabilities; the client sends `initialized` as confirmation.

- **`LSPServerCapabilities`**: declares the full set of capabilities the FizzLSP server supports:
  - `textDocumentSync`: `TextDocumentSyncKind.Incremental` (2) -- the server supports incremental document synchronization, receiving only changed text ranges rather than full document contents on each edit. This is essential for responsive editing -- resending 500 lines of FizzLang source on every keystroke is wasteful even for a simulated language server.
  - `completionProvider`: `{ triggerCharacters: [".", "%", "(", " "], resolveProvider: true }` -- completions are triggered by space (after keywords), percent (modulo operator context), open paren (function call), and period (potential future member access). The `resolveProvider` flag indicates that completion items can be lazily resolved with additional documentation on demand.
  - `hoverProvider`: `true` -- hover information available for all identifiers, keywords, and operators.
  - `definitionProvider`: `true` -- go-to-definition for variables, rules, and functions.
  - `referencesProvider`: `true` -- find all references to a symbol.
  - `renameProvider`: `{ prepareProvider: true }` -- rename with prepare step to validate renameability and compute the default rename range before committing the edit.
  - `documentSymbolProvider`: `true` -- document outline showing rules, let-bindings, and evaluate statements.
  - `workspaceSymbolProvider`: `true` -- project-wide symbol search.
  - `semanticTokensProvider`: `{ full: true, range: true, legend: { tokenTypes: [...], tokenModifiers: [...] } }` -- full semantic token support with both full-document and range-based token requests.
  - `codeActionProvider`: `{ codeActionKinds: ["quickfix", "refactor.extract", "refactor.rewrite", "source.fixAll"] }` -- code actions for quick fixes and refactoring.
  - `documentFormattingProvider`: `true` -- whole-document formatting.
  - `diagnosticProvider`: `{ interFileDiagnostics: false, workspaceDiagnostics: false }` -- diagnostics are per-document (FizzLang files are self-contained; there are no imports because user-defined functions do not exist).
- **`InitializeHandler`**: processes the `initialize` request. Reads the client's capabilities to determine supported features (e.g., whether the client supports `workspace/configuration`, `window/workDoneProgress`, `textDocument/publishDiagnostics` with related information). Stores client capabilities for conditional feature activation. Returns the `InitializeResult` containing the server's capabilities and server info (`{ name: "FizzLSP", version: "1.0.0" }`). Transitions the server state from `UNINITIALIZED` to `INITIALIZING`.
- **`InitializedHandler`**: processes the `initialized` notification. Transitions the server from `INITIALIZING` to `RUNNING`. At this point, the server begins accepting language feature requests. Optionally registers dynamic capabilities if the client supports `client/registerCapability`.
- **`ShutdownHandler`**: processes the `shutdown` request. Transitions the server to `SHUTTING_DOWN`. Returns a null result. After shutdown, the server rejects all requests except `exit`.
- **`ExitHandler`**: processes the `exit` notification. Terminates the server. Exit code 0 if `shutdown` was received first, exit code 1 otherwise (per the LSP specification).
- **`LSPServerState`**: state machine for the server lifecycle: `UNINITIALIZED` -> `INITIALIZING` (after `initialize` response sent) -> `RUNNING` (after `initialized` received) -> `SHUTTING_DOWN` (after `shutdown` request) -> `TERMINATED` (after `exit`). Invalid transitions raise `LSPProtocolError`. This mirrors FizzDAP's `SessionState` pattern but with LSP-specific states.

### Document Synchronization

The server maintains an in-memory mirror of every open document. Incremental synchronization means the client sends only the text ranges that changed, and the server applies those edits to its buffer.

- **`TextDocumentItem`**: represents an open document with its URI, language ID (`"fizzlang"`), version number, and full text content. The version number increases monotonically with each edit and is used to detect out-of-order notifications.
- **`TextDocumentManager`**: manages the set of open documents. Handles three notifications:
  - `textDocument/didOpen`: creates a new `TextDocumentItem` with the initial content. Triggers a full analysis of the document (lex, parse, type-check) and publishes initial diagnostics.
  - `textDocument/didChange`: applies incremental content changes to the document buffer. Each change specifies a `range` (start line/character to end line/character) and the `text` to replace that range with. The manager applies changes in order, updating the document's content and incrementing the version. After applying all changes, triggers incremental re-analysis: the server re-lexes only the affected region when possible, re-parses the entire document (FizzLang's grammar is simple enough that full re-parse is sub-millisecond even for the maximum practical file size), and re-type-checks. Publishes updated diagnostics.
  - `textDocument/didClose`: removes the document from the manager and clears its diagnostics by publishing an empty diagnostic array.
- **`IncrementalSyncEngine`**: applies text edits to a document buffer. Converts line/character positions to byte offsets, performs the text replacement, and recomputes line start offsets for subsequent position calculations. Handles edge cases: insertions at document end, deletions spanning multiple lines, replacements that change the number of lines. The engine validates that incoming ranges are within document bounds and rejects edits to closed documents.

### Analysis Pipeline

Every document change triggers a re-analysis pipeline that produces diagnostics, an AST, a symbol table, and token classifications. The pipeline integrates the existing FizzLang lexer, parser, and type checker with additional analysis passes.

- **`AnalysisPipeline`**: orchestrates the sequence of analyses performed on each document change:
  1. **Lexical analysis**: runs `fizzlang.Lexer(source).tokenize()` to produce a token stream. If the lexer raises `FizzLangLexerError`, the error is captured as a diagnostic with severity `Error` at the error's source location. The pipeline continues with the partial token stream (all tokens produced before the error).
  2. **Syntactic analysis**: runs `fizzlang.Parser(tokens).parse()` to produce a `ProgramNode` AST. If the parser raises `FizzLangParseError`, the error is captured as a diagnostic with the expected and found tokens. Recovery: the pipeline attempts error recovery by inserting synthetic tokens at the error location and retrying. Up to 3 recovery attempts per parse to produce a partial AST for downstream analysis even in the presence of syntax errors.
  3. **Semantic analysis**: runs `fizzlang.TypeChecker().check(ast)` against the (possibly partial) AST. `FizzLangTypeError` exceptions become `Error` diagnostics. Warnings returned by the type checker become `Warning` diagnostics.
  4. **Dependent type analysis**: runs a lightweight pass from the dependent type system to check proof obligations for any `evaluate` statements in the document. `TypeCheckError` and `ProofObligationError` are captured as `Information` diagnostics (they represent proof-theoretic observations, not programming errors).
  5. **Symbol collection**: walks the AST to build a `SymbolTable` containing all defined symbols (rule names, let-binding names, stdlib function references) with their definition locations, types, and scopes.
  6. **Semantic token classification**: walks the token stream and AST together to produce semantic token data (token type and modifiers for each span) for syntax highlighting.
- **`AnalysisResult`**: the product of the analysis pipeline: `diagnostics` (list of LSP `Diagnostic` objects), `ast` (the parsed `ProgramNode` or `None`), `tokens` (the lexed token list), `symbol_table` (the collected symbols), `semantic_tokens` (the classified token spans), `analysis_time_ms` (pipeline duration for performance monitoring).
- **`SymbolTable`**: maps symbol names to `SymbolInfo` records containing: `name`, `kind` (rule, variable, function, keyword), `definition_location` (URI, line, character), `type_info` (inferred type string, e.g., `"int"`, `"string"`, `"bool"`, `"(int) -> bool"`), `documentation` (docstring extracted from adjacent comments or stdlib documentation), `references` (list of locations where the symbol is used), `scope` (the enclosing scope -- top-level or the specific rule/evaluate statement). The symbol table is rebuilt on every document change because FizzLang's scoping rules are simple (all let-bindings are top-level) and the rebuild is sub-millisecond.

### Completion Provider

Provides context-aware completion suggestions triggered by typing or by explicit completion requests (`Ctrl+Space`).

- **`CompletionProvider`**: implements `textDocument/completion`. Determines the completion context by analyzing the cursor position relative to the token stream and partial AST:
  - **Statement-level completion**: when the cursor is at a position where a new statement can begin (start of line, after a completed statement), suggests `rule`, `let`, and `evaluate` with snippet templates:
    - `rule`: inserts `rule ${1:name} when ${2:condition} emit ${3:expression} priority ${4:0}` with tabstops for each field
    - `let`: inserts `let ${1:name} = ${2:expression}`
    - `evaluate`: inserts `evaluate ${1:start} to ${2:end}`
  - **Keyword completion**: after `rule NAME`, suggests `when`. After `when CONDITION`, suggests `emit`. After `emit EXPRESSION`, suggests `priority`. After `evaluate START`, suggests `to`. These follow the FizzLang grammar's required keyword sequences.
  - **Variable completion**: in expression context, suggests all let-bound variables defined before the cursor position (respecting definition order), the sacred variable `n`, and boolean literals `true` and `false`.
  - **Function completion**: in expression context, suggests stdlib functions with their signatures and documentation:
    - `is_prime(n)`: `"Trial-division primality test. Returns true if n is prime."`
    - `fizzbuzz(n)`: `"Evaluate standard FizzBuzz for a single number. Returns the classification string."`
    - `range(a, b)`: `"Return integers from a to b inclusive."`
  - **Operator completion**: after an expression, suggests arithmetic operators (`+`, `-`, `*`, `/`, `%`), comparison operators (`==`, `!=`, `<`, `>`, `<=`, `>=`), and boolean operators (`and`, `or`).
  - **Configuration key completion**: when editing inside a string literal in a context that expects a configuration key (detected by analyzing the enclosing AST node), suggests known configuration keys from `ConfigurationManager`.
  - **FizzFile instruction completion**: when the document URI ends with `.fizzfile`, switches to FizzFile completion mode and suggests FizzFile instructions: `FROM`, `FIZZ`, `BUZZ`, `RUN`, `COPY`, `ENV`, `ENTRYPOINT`, `LABEL`, `EXPOSE`, `VOLUME`, `WORKDIR`, `USER`, `HEALTHCHECK`.
  - **FizzGrammar terminal completion**: when the document URI ends with `.fizzgrammar` or the content begins with a BNF-style production, suggests grammar terminals and non-terminals from the FizzGrammar vocabulary: `::=`, `|`, `;`, `IDENTIFIER`, `NUMBER`, `STRING`, and non-terminal names from the built-in FizzBuzz Classification grammar.
- **`CompletionItem`**: each suggestion includes `label` (display text), `kind` (LSP CompletionItemKind -- Keyword, Variable, Function, Snippet, Operator, Property), `detail` (short type or category string), `documentation` (full Markdown documentation), `insertText` (the text to insert, potentially with snippet syntax), `insertTextFormat` (PlainText or Snippet), and `sortText` (ordering key to ensure contextually relevant items appear first -- keywords before variables, variables before functions, operators last).
- **`CompletionResolveHandler`**: implements `completionItem/resolve`. When a completion item is selected but its full documentation was not included in the initial response (for performance -- the initial list may contain dozens of items), the resolve request lazily loads the item's full documentation, additional text edits (e.g., adding a missing `let` binding), and commit characters.

### Diagnostic Provider

Publishes diagnostics (errors, warnings, information, hints) to the client after every document change.

- **`DiagnosticPublisher`**: converts `AnalysisResult.diagnostics` into LSP `textDocument/publishDiagnostics` notifications. Each diagnostic includes:
  - `range`: the source location of the error (line and character, zero-indexed as LSP requires). For lexer errors, the range spans the offending character. For parse errors, the range spans the unexpected token. For type errors, the range spans the offending AST node (computed by walking the AST to find the node matching the error's description). For dependent type errors, the range spans the `evaluate` statement that generated the proof obligation.
  - `severity`: `Error` (1) for lexer, parser, and type checker errors. `Warning` (2) for type checker warnings (e.g., empty program). `Information` (3) for dependent type observations. `Hint` (4) for style suggestions.
  - `code`: a machine-readable error code following the platform's exception code scheme: `"EFP-FL10"` for base FizzLang errors, `"EFP-FL11"` for lexer errors, `"EFP-FL12"` for parse errors, `"EFP-FL13"` for type errors, `"EFP-FL14"` for runtime errors (shown as warnings since runtime errors cannot occur in a static analysis pass).
  - `source`: always `"FizzLSP"`.
  - `message`: the human-readable error message from the exception.
  - `relatedInformation`: for "undefined variable" errors, includes a related location pointing to the nearest let-binding with a similar name (Levenshtein distance <= 2), if one exists, with the message "Did you mean '...'?". For duplicate rule name errors, includes a related location pointing to the original rule definition.
  - `tags`: `Unnecessary` (1) for unused let-bindings detected by cross-referencing the symbol table's reference lists. `Deprecated` (2) is not used because FizzLang has no deprecation mechanism -- deprecation implies evolution, and FizzLang is complete as designed.
- **`DiagnosticThrottler`**: debounces diagnostic publication to avoid flooding the client during rapid typing. After each document change, the throttler waits 150ms (configurable) before publishing diagnostics. If another change arrives within the window, the timer resets. This ensures that intermediate states during fast typing (e.g., typing `rule fizz when` character by character) do not generate 14 diagnostic notifications for 14 intermediate invalid states.

### Go-to-Definition

Navigates from a symbol reference to its definition.

- **`DefinitionProvider`**: implements `textDocument/definition`. Given a cursor position, identifies the symbol under the cursor (by finding the token at that position and resolving it through the symbol table) and returns the definition location:
  - **Let-bound variables**: navigating from an `IdentifierNode` reference to the `LetNode` where the variable was defined. The definition location is the position of the variable name in the `let` statement.
  - **Rule names**: navigating from a rule name reference (in comments or evaluate context) to the `RuleNode` where the rule was declared. The definition location is the position of the rule name in the `rule` statement.
  - **Stdlib functions**: navigating from a `FunctionCallNode` to a synthetic definition location within the FizzLSP server that represents the stdlib function. Since stdlib functions are defined in Python (in `fizzlang.StdLib`), the definition location points to the corresponding method in `fizzlang.py`. The server resolves the file path and line number of `StdLib.is_prime`, `StdLib.fizzbuzz`, or `StdLib.range_inclusive` at initialization time.
  - **The sacred variable `n`**: `n` has no definition site -- it is an intrinsic of the language, like `this` in Java or `self` in Python. Go-to-definition on `n` returns `null` (no definition found). A future enhancement could return a synthetic location with documentation explaining that `n` is the number being evaluated, but for now, the hover provider serves that purpose.
  - **Keywords**: go-to-definition on keywords (`rule`, `when`, `emit`, `evaluate`, `let`, `priority`, `to`, `and`, `or`, `not`) returns `null`. Keywords are not user-defined symbols.

### Hover Provider

Displays type information, documentation, and contextual details when the user hovers over a symbol.

- **`HoverProvider`**: implements `textDocument/hover`. Given a cursor position, identifies the entity under the cursor and returns a `Hover` response with Markdown content:
  - **Variables (let-bound)**: displays the variable name, its inferred type (computed by evaluating the right-hand side of the `let` binding: integer literals produce `int`, string literals produce `string`, boolean literals produce `bool`, arithmetic expressions produce `int`, comparison expressions produce `bool`, function calls produce the function's return type), and the defining expression. Example: `let divisor = 3` -> `(variable) divisor: int\n\nDefined at line 2: let divisor = 3`.
  - **The sacred variable `n`**: displays `(intrinsic) n: int` and the documentation "The number being evaluated. The only value that matters in FizzBuzz. All other variables exist in service of `n`."
  - **Stdlib functions**: displays the function signature and full documentation. Example: `is_prime` -> `(function) is_prime(n: int) -> bool\n\nTrial-division primality test. O(sqrt(n)) because we're not barbarians.\n\nArity: 1`.
  - **Rule names**: displays the rule definition summary: name, condition (as source text), emit expression, priority, and any type checker warnings. Example: `rule fizz when n % 3 == 0 emit "Fizz" priority 1` -> `(rule) fizz\n\nCondition: n % 3 == 0\nEmit: "Fizz"\nPriority: 1`.
  - **Keywords**: displays documentation for the keyword:
    - `rule`: "Declares a FizzBuzz classification rule. Syntax: `rule NAME when CONDITION emit EXPRESSION [priority N]`"
    - `let`: "Binds a value to a name. Syntax: `let NAME = EXPRESSION`"
    - `evaluate`: "Evaluates a range of numbers through the declared rules. Syntax: `evaluate START to END`"
    - `when`: "Introduces the condition clause of a rule."
    - `emit`: "Introduces the output expression of a rule."
    - `priority`: "Sets the priority of a rule (non-negative integer, higher values take precedence)."
  - **Operators**: displays the operator's semantics. `%` -> "Modulo operator. Returns the remainder of integer division. The single most important operator in FizzBuzz." `==` -> "Equality comparison. Returns `true` if both operands are equal."
  - **Integer literals**: displays the literal's value and its FizzBuzz classification if the value can be evaluated. Example: hovering over `15` -> `(literal) 15: int\n\nFizzBuzz classification: FizzBuzz (15 % 3 == 0 and 15 % 5 == 0)`.

### References Provider

Locates all references to a symbol within the document.

- **`ReferencesProvider`**: implements `textDocument/references`. Given a cursor position and an `includeDeclaration` flag, returns all locations where the symbol at the cursor position is referenced:
  - **Let-bound variables**: collects all `IdentifierNode` AST nodes whose `name` matches the variable name. If `includeDeclaration` is true, includes the `LetNode` definition site.
  - **Rule names**: collects all references to the rule name. Since FizzLang does not support rule-to-rule references in the grammar (rules are declarations, not callable entities), rule references are limited to the declaration itself unless the rule name appears in comments. The provider scans both AST nodes and comment tokens for the rule name.
  - **Stdlib functions**: collects all `FunctionCallNode` AST nodes whose `name` matches the function. `includeDeclaration` includes the synthetic stdlib definition location.
  - **The sacred variable `n`**: collects all `NVarNode` AST nodes. Since `n` has no definition site, `includeDeclaration` has no effect.

### Rename Provider

Performs scope-aware symbol renaming with conflict detection.

- **`RenameProvider`**: implements `textDocument/rename` and `textDocument/prepareRename`:
  - **Prepare rename** (`textDocument/prepareRename`): validates that the symbol under the cursor is renameable (variables, rule names, and function calls are renameable; keywords, operators, literals, and `n` are not). Returns the range of the symbol to be renamed and its current name as the default new name. If the symbol is not renameable, returns an error response with an explanatory message (e.g., "Cannot rename the sacred variable 'n'. It is immutable in name as in purpose.").
  - **Rename** (`textDocument/rename`): computes a `WorkspaceEdit` containing all text edits needed to rename the symbol:
    - Validates the new name against FizzLang's identifier rules (must start with a letter or underscore, contain only alphanumeric characters and underscores, must not be a reserved keyword, must not be `n`).
    - Checks for conflicts: if the new name matches an existing let-binding, rule name, or stdlib function name, the rename is rejected with an error message identifying the conflict (e.g., "Cannot rename to 'fizz': a rule with that name already exists at line 3").
    - Collects all reference locations (via the references provider) and produces a `TextEdit` for each, replacing the old name with the new name.
    - For rule names, also renames any occurrences in comments that match the pattern (heuristic: a word boundary match of the old name in comment text is considered a reference).

### Workspace Symbol Provider

Searches for symbols across the workspace.

- **`WorkspaceSymbolProvider`**: implements `workspace/symbol`. Given a query string, searches all open documents' symbol tables for matching symbols. Returns a list of `SymbolInformation` objects containing the symbol name, kind (mapped to LSP `SymbolKind`: rule -> Function, let-binding -> Variable, evaluate -> Event, stdlib function -> Method), location (URI and range), and container name (the document's file name). The search is case-insensitive and supports substring matching. An empty query returns all symbols.

### Semantic Token Provider

Provides semantic token classifications for syntax highlighting.

- **`SemanticTokenProvider`**: implements `textDocument/semanticTokens/full` and `textDocument/semanticTokens/range`. Walks the token stream and produces semantic token data encoded in the LSP delta-encoded format (each token is encoded as 5 integers: delta line, delta start character, length, token type index, token modifier bitset).
  - **Token type legend**: `keyword` (0), `variable` (1), `function` (2), `string` (3), `number` (4), `operator` (5), `comment` (6), `type` (7), `parameter` (8), `property` (9), `namespace` (10), `enumMember` (11).
  - **Token modifier legend**: `declaration` (0), `definition` (1), `readonly` (2), `static` (3), `deprecated` (4), `modification` (5), `documentation` (6), `defaultLibrary` (7).
  - **Classification rules**:
    - `TokenType.RULE`, `TokenType.WHEN`, `TokenType.EMIT`, `TokenType.EVALUATE`, `TokenType.TO`, `TokenType.LET`, `TokenType.PRIORITY`, `TokenType.AND`, `TokenType.OR`, `TokenType.NOT`, `TokenType.TRUE`, `TokenType.FALSE`: semantic type `keyword`.
    - `TokenType.N_VAR`: semantic type `variable` with modifier `readonly` (because `n` cannot be reassigned).
    - `TokenType.IDENTIFIER` at a `LetNode.name` position: semantic type `variable` with modifier `declaration`.
    - `TokenType.IDENTIFIER` at an `IdentifierNode` reference position: semantic type `variable`.
    - `TokenType.IDENTIFIER` at a `RuleNode.name` position: semantic type `function` with modifier `declaration`.
    - `TokenType.IDENTIFIER` at a `FunctionCallNode.name` position: semantic type `function` with modifier `defaultLibrary`.
    - `TokenType.INTEGER`: semantic type `number`.
    - `TokenType.STRING`: semantic type `string`.
    - `TokenType.PLUS`, `TokenType.MINUS`, `TokenType.STAR`, `TokenType.SLASH`, `TokenType.PERCENT`, `TokenType.EQUALS`, `TokenType.NOT_EQUALS`, `TokenType.LESS_THAN`, `TokenType.GREATER_THAN`, `TokenType.LESS_EQUAL`, `TokenType.GREATER_EQUAL`, `TokenType.ASSIGN`: semantic type `operator`.
    - Comment tokens (lines starting with `#`): semantic type `comment`.
  - **Range support**: `textDocument/semanticTokens/range` returns tokens only within the requested range, enabling efficient partial highlighting for large documents (though no FizzLang document has ever exceeded 50 lines, the protocol supports it, so the implementation supports it).

### Code Action Provider

Offers quick fixes and refactoring suggestions in response to diagnostics and cursor context.

- **`CodeActionProvider`**: implements `textDocument/codeAction`. Returns code actions relevant to the current diagnostics and cursor position:
  - **Quick fix: suggest similar identifier**: when a diagnostic reports an undefined variable (type error `EFP-FL13`), and the symbol table contains an identifier within Levenshtein distance 2 of the undefined name, offers a code action to replace the undefined reference with the similar identifier. Example: `let divsor = 3` followed by `n % divisor` (where `divisor` is not defined but `divsor` is) -> quick fix: "Replace 'divisor' with 'divsor'".
  - **Quick fix: add missing let-binding**: when a diagnostic reports an undefined variable, offers a code action to insert a `let` binding for the undefined variable before the line where it is used. The binding's value is left as a placeholder (`0` for identifiers in arithmetic context, `""` for identifiers in string context, `true` for identifiers in boolean context).
  - **Quick fix: fix duplicate rule name**: when a diagnostic reports a duplicate rule name, offers a code action to append a numeric suffix to the duplicate rule name (e.g., `fizz` -> `fizz_2`).
  - **Quick fix: fix negative priority**: when a diagnostic reports a negative priority, offers a code action to change the priority to `0`.
  - **Refactoring: extract expression to let-binding**: when the cursor is on an expression that appears more than once in the document, offers a refactoring to extract the expression into a `let` binding and replace all occurrences with the variable reference. The new variable name is derived from the expression (e.g., `n % 3` -> `let n_mod_3 = n % 3`).
  - **Refactoring: reorder rules by priority**: when the cursor is inside a rule block and rules are not ordered by priority (highest first), offers a refactoring that reorders all rules in descending priority order.
  - **Source action: format document**: equivalent to `textDocument/formatting`, offered as a code action so it appears in the quick-fix menu alongside error-specific actions.

### Document Formatting Provider

Formats FizzLang documents according to the canonical style.

- **`FormattingProvider`**: implements `textDocument/formatting`. Produces a list of `TextEdit` objects that transform the document into canonical FizzLang style:
  - **Blank lines**: exactly one blank line between statements. No blank lines within a statement. Leading and trailing blank lines are removed.
  - **Comments**: comment lines are preserved in place. Inline comments (if they existed) would be separated from code by two spaces (FizzLang does not have inline comments, but the formatter is ready for the day they arrive).
  - **Indentation**: FizzLang has no block structure, so indentation is always zero. Any indented lines are dedented.
  - **Spacing**: single space between keywords and their arguments. Single space around operators. No space inside parentheses. No space before commas. Single space after commas.
  - **Keywords**: canonicalized to lowercase (FizzLang keywords are case-insensitive, but the canonical form is lowercase).
  - **Trailing whitespace**: removed from all lines.
  - **Final newline**: document ends with exactly one newline.
  The formatter operates on the token stream rather than the raw text, ensuring that formatting respects token boundaries. Tokens are re-emitted with canonical spacing according to the rules above.

### Document Symbol Provider

Provides the document outline (symbol tree) for the file explorer and breadcrumb navigation.

- **`DocumentSymbolProvider`**: implements `textDocument/documentSymbol`. Returns a list of `DocumentSymbol` objects representing the hierarchical structure of the document:
  - **Rules**: `SymbolKind.Function`, with `detail` showing the condition and emit expression, and `children` containing the rule's sub-components (condition as a `SymbolKind.Boolean`, emit expression as a `SymbolKind.String`, priority as a `SymbolKind.Number`).
  - **Let-bindings**: `SymbolKind.Variable`, with `detail` showing the bound expression.
  - **Evaluate statements**: `SymbolKind.Event`, with `detail` showing the range expression.
  The outline enables IDE features like breadcrumb navigation ("you are inside rule 'fizz' > condition") and the document outline panel.

### FizzLSP Server

The main server class that wires together all providers, the transport layer, and the initialization handshake.

- **`FizzLSPServer`**: the top-level server class.
  - Manages server state via `LSPServerState`.
  - Instantiates `LSPDispatcher` and registers all handlers: `initialize`, `initialized`, `shutdown`, `exit`, `textDocument/didOpen`, `textDocument/didChange`, `textDocument/didClose`, `textDocument/completion`, `completionItem/resolve`, `textDocument/hover`, `textDocument/definition`, `textDocument/references`, `textDocument/rename`, `textDocument/prepareRename`, `workspace/symbol`, `textDocument/semanticTokens/full`, `textDocument/semanticTokens/range`, `textDocument/codeAction`, `textDocument/formatting`, `textDocument/documentSymbol`, `textDocument/publishDiagnostics`.
  - Instantiates `TextDocumentManager`, `AnalysisPipeline`, `CompletionProvider`, `DiagnosticPublisher`, `DefinitionProvider`, `HoverProvider`, `ReferencesProvider`, `RenameProvider`, `WorkspaceSymbolProvider`, `SemanticTokenProvider`, `CodeActionProvider`, `FormattingProvider`, `DocumentSymbolProvider`.
  - Provides `handle_message(raw: str) -> str | None` method that decodes an incoming message, dispatches to the appropriate handler, and encodes the response (or returns `None` for notifications that require no response).
  - Provides `simulate_session(messages: list[str]) -> list[str]` method that processes a sequence of raw LSP messages and returns the sequence of responses and notifications. This is the primary testing interface -- test cases construct a sequence of JSON-RPC messages simulating an editor session and assert on the server's responses.
- **`FizzLSPMetrics`**: tracks server performance metrics: number of requests processed, average response time per method, number of diagnostics published, number of completions served, number of definitions resolved. Exposed via the `--fizzlsp-metrics` CLI flag.

### FizzLSP Dashboard

An ASCII dashboard displaying language server status, active documents, symbol counts, diagnostic summaries, and protocol statistics.

- **`FizzLSPDashboard`**: renders a box-drawing ASCII dashboard (following the established pattern of every other subsystem's dashboard) showing:
  - Server state and uptime.
  - Connected client capabilities summary.
  - Active documents: URI, version, symbol count, diagnostic count.
  - Total symbols across all documents: rules, variables, evaluate statements.
  - Diagnostic breakdown: errors, warnings, information, hints.
  - Protocol statistics: requests received, responses sent, notifications sent, average response latency.
  - The LSP Complexity Index: lines of `fizzlsp.py` divided by lines of core FizzBuzz logic. Expected to exceed 200:1.

### CLI Integration

- **CLI Flags**:
  - `--fizzlsp`: enable the FizzLSP language server subsystem.
  - `--fizzlsp-analyze <file.fizz>`: run the full analysis pipeline on a FizzLang source file and print diagnostics, symbol table, and semantic tokens.
  - `--fizzlsp-complete <file.fizz> <line> <col>`: simulate a completion request at the given cursor position and print the completion list.
  - `--fizzlsp-hover <file.fizz> <line> <col>`: simulate a hover request and print the hover content.
  - `--fizzlsp-definition <file.fizz> <line> <col>`: simulate a go-to-definition request and print the definition location.
  - `--fizzlsp-references <file.fizz> <line> <col>`: simulate a find-references request and print all reference locations.
  - `--fizzlsp-rename <file.fizz> <line> <col> <new_name>`: simulate a rename request and print the workspace edit.
  - `--fizzlsp-format <file.fizz>`: simulate a formatting request and print the formatted document.
  - `--fizzlsp-symbols <file.fizz>`: print the document symbol outline.
  - `--fizzlsp-tokens <file.fizz>`: print the semantic token classifications for every token.
  - `--fizzlsp-simulate`: run a predefined editor simulation session (open a sample FizzLang document, make edits, request completions, hover, definition, rename) and print the full JSON-RPC message exchange.
  - `--fizzlsp-metrics`: print language server performance metrics.
  - `--fizzlsp-dashboard`: display the ASCII dashboard.

### Middleware Integration

- **`FizzLSPMiddleware`**: middleware component that records language server activity during FizzBuzz evaluation. When a FizzBuzz evaluation is in progress, the middleware notes the LSP server state, the number of open documents, the total diagnostic count, and the analysis pipeline latency. This data is included in the middleware pipeline's evaluation context, because even the act of evaluating FizzBuzz should be aware that someone, somewhere, is editing a FizzLang program.

### Feature Flag Integration

- **`FizzLSPFeature`**: feature flag registration with the platform's feature flag system. The `fizzlsp` feature flag controls whether the language server subsystem is initialized. When disabled, all `--fizzlsp-*` CLI flags are no-ops and the middleware component reports "FizzLSP: disabled" in the evaluation context.

### Configuration Mixin

- **`FizzLSPConfigMixin`**: configuration mixin for the `ConfigurationManager` singleton. Provides configuration keys:
  - `fizzlsp.transport` (default: `"stdio"`): transport type (`"stdio"` or `"tcp"`).
  - `fizzlsp.tcp_port` (default: `5007`): TCP port for the TCP transport.
  - `fizzlsp.diagnostic_debounce_ms` (default: `150`): debounce interval for diagnostic publication.
  - `fizzlsp.max_completion_items` (default: `50`): maximum number of completion items returned per request.
  - `fizzlsp.semantic_tokens_enabled` (default: `true`): whether to compute semantic tokens.
  - `fizzlsp.dependent_type_diagnostics` (default: `true`): whether to include dependent type observations in diagnostics.

---

## Why This Is Necessary

The Enterprise FizzBuzz Platform has invested substantially in developer tooling for the FizzLang DSL. The lexer, parser, type checker, interpreter, REPL, formal grammar engine, and debug adapter represent a complete language implementation across the compilation pipeline. Every stage of language processing is present: source text in, structured output out. The one stage conspicuously absent is the interactive editing stage -- the stage where a developer is actively writing code and needs real-time feedback.

The Language Server Protocol is the industry-standard solution for interactive language intelligence. Every major language runtime ships an LSP implementation: TypeScript has `tsserver`, Rust has `rust-analyzer`, Python has `pylsp` and `pyright`, Go has `gopls`, C++ has `clangd`, Java has `eclipse.jdt.ls`. Languages without LSP implementations are languages that have conceded the IDE experience to text editors with no more intelligence than `grep`. FizzLang currently occupies this category. A developer writing FizzLang source receives less assistance than a developer editing a Markdown file (which at least gets preview rendering).

The platform already possesses all the semantic knowledge required for language intelligence. The lexer knows the token types and their source locations. The parser knows the grammar and the AST structure. The type checker knows about variable scoping, rule uniqueness, function arities, and expression types. The dependent type system knows about proof obligations and type-level properties. The grammar engine knows about FIRST sets and LL(1) parse table entries. All of this knowledge is locked inside batch-mode tools. LSP is the key that converts batch-mode analysis into interactive, as-you-type intelligence.

FizzDAP demonstrated that the platform can implement a JSON-RPC protocol with Content-Length framing, capability negotiation, session state machines, and method dispatch. FizzLSP uses the identical wire protocol, the identical message framing, and a structurally similar dispatcher architecture. The marginal complexity of adding LSP is lower than the complexity of having added DAP, because the protocol patterns have already been established.

The language server is the bridge between the language implementation and the developer experience. Without it, FizzLang is a command-line-only language in an IDE-first world.

---

## Integration Points

- **FizzLang** (`fizzlang.py`): the language server's analysis pipeline directly invokes `Lexer.tokenize()`, `Parser.parse()`, and `TypeChecker.check()` from the FizzLang module. The semantic token provider maps FizzLang `TokenType` enum values to LSP semantic token types. The completion provider uses FizzLang's `_KEYWORDS` dictionary and `TypeChecker.STDLIB_FUNCTIONS` as completion sources.
- **FizzDAP** (`fizzdap.py`): the JSON-RPC transport layer (`LSPMessage`) follows the same `Content-Length` framing pattern established by `DAPMessage`. The server state machine (`LSPServerState`) mirrors `SessionState`. The capability negotiation handshake follows the same pattern as DAP initialization.
- **Dependent Types** (`dependent_types.py`): the analysis pipeline includes a pass that checks proof obligations from the dependent type system. `TypeCheckError`, `ProofObligationError`, and `UnificationError` exceptions are mapped to LSP `Information` diagnostics.
- **FizzGrammar** (`fizzlang.py`): the completion provider for `.fizzgrammar` files uses `Grammar`, `Symbol`, `terminal`, and `non_terminal` from the grammar engine. The FIRST set data from `FirstFollowComputer` informs completion ordering for grammar documents.
- **FizzFile** (`fizzregistry.py`): the completion provider for `.fizzfile` documents suggests FizzFile instructions (`FROM`, `FIZZ`, `BUZZ`, etc.) from FizzRegistry's FizzFile parser.
- **ConfigurationManager**: the configuration mixin provides `fizzlsp.*` configuration keys accessible through the platform's standard configuration precedence chain (CLI flags > environment variables > config.yaml).
- **Feature Flags**: the `fizzlsp` feature flag controls subsystem initialization through the platform's standard feature flag infrastructure.
- **Middleware Pipeline**: `FizzLSPMiddleware` integrates with the standard middleware chain, recording language server activity in the evaluation context.

---

## Estimated Scale

~3,500 lines of language server implementation:
- ~250 lines of JSON-RPC transport layer (`LSPMessage`, `StdioTransport`, `TCPTransport`, `LSPDispatcher`)
- ~200 lines of initialization handshake (`LSPServerCapabilities`, `InitializeHandler`, `InitializedHandler`, `ShutdownHandler`, `ExitHandler`, `LSPServerState`)
- ~200 lines of document synchronization (`TextDocumentItem`, `TextDocumentManager`, `IncrementalSyncEngine`)
- ~300 lines of analysis pipeline (`AnalysisPipeline`, `AnalysisResult`, `SymbolTable`, `SymbolInfo`)
- ~400 lines of completion provider (`CompletionProvider`, `CompletionItem`, `CompletionResolveHandler`, context analysis, FizzFile/FizzGrammar modes)
- ~200 lines of diagnostic provider (`DiagnosticPublisher`, `DiagnosticThrottler`, diagnostic mapping, related information)
- ~200 lines of go-to-definition provider (`DefinitionProvider`, variable/rule/function/stdlib resolution)
- ~300 lines of hover provider (`HoverProvider`, variable/function/rule/keyword/operator/literal hover content)
- ~150 lines of references provider (`ReferencesProvider`, AST walking, comment scanning)
- ~250 lines of rename provider (`RenameProvider`, prepare rename, conflict detection, workspace edit generation)
- ~100 lines of workspace symbol provider (`WorkspaceSymbolProvider`, cross-document search)
- ~250 lines of semantic token provider (`SemanticTokenProvider`, token classification, delta encoding, range support)
- ~250 lines of code action provider (`CodeActionProvider`, quick fixes, refactoring suggestions)
- ~150 lines of formatting provider (`FormattingProvider`, token-based reformatting)
- ~100 lines of document symbol provider (`DocumentSymbolProvider`, outline generation)
- ~150 lines of FizzLSP server (`FizzLSPServer`, handler registration, message dispatch, simulation interface)
- ~100 lines of metrics and dashboard (`FizzLSPMetrics`, `FizzLSPDashboard`)
- ~150 lines of CLI integration, middleware, feature flag, configuration mixin

~500 lines of tests:
- Transport layer tests (encode/decode, Content-Length validation, request/response/notification dispatch)
- Initialization handshake tests (capability negotiation, state machine transitions, shutdown/exit)
- Document sync tests (open/change/close, incremental edits, version tracking)
- Completion tests (statement-level, keyword, variable, function, operator, FizzFile, FizzGrammar)
- Diagnostic tests (lexer errors, parse errors, type errors, dependent type observations, throttling)
- Definition tests (variable, rule, stdlib function, `n`, keyword)
- Hover tests (variable, function, rule, keyword, operator, literal with FizzBuzz classification)
- References tests (variable references, rule references, `n` references)
- Rename tests (variable rename, rule rename, conflict detection, unrenameable symbols)
- Semantic token tests (full document, range, all token types and modifiers)
- Code action tests (typo suggestion, missing let-binding, extract expression)
- Formatting tests (spacing, blank lines, keyword case, trailing whitespace)
- Integration tests (full editor simulation sessions)

**Total: ~4,000 lines**

# PLAN: FizzGrammar -- Formal Grammar & Parser Generator

**Status:** READY FOR IMPLEMENTATION
**Target file:** `enterprise_fizzbuzz/infrastructure/formal_grammar.py` (~600 lines)

---

## 1. Overview

Add a formal grammar subsystem that provides BNF/EBNF grammar specification, FIRST/FOLLOW set computation, LL(1) classification, left-recursion and ambiguity detection, a parser generator that compiles grammars to recursive-descent parsers, and an ASCII dashboard summarizing grammar health. The subsystem ships a built-in FizzBuzz Classification grammar as its showcase grammar.

## 2. Architecture

All code in a single infrastructure module: `formal_grammar.py`. No domain or application layer changes beyond exceptions and config wiring.

### Core Classes

| Class | Responsibility |
|-------|---------------|
| `Terminal` | Represents a terminal symbol (literal or regex pattern) |
| `NonTerminal` | Represents a non-terminal symbol |
| `Production` | A single production rule: LHS non-terminal -> sequence of symbols |
| `Grammar` | Container for productions, terminals, non-terminals, start symbol |
| `GrammarParser` | Parses BNF/EBNF text into a `Grammar` object |
| `FirstFollowComputer` | Fixed-point iteration for FIRST and FOLLOW sets |
| `LL1Classifier` | Determines if a grammar is LL(1); reports conflicts |
| `LeftRecursionDetector` | DFS cycle detection for direct/indirect left recursion |
| `AmbiguityAnalyzer` | Bounded derivation search for ambiguous strings |
| `UnreachableSymbolDetector` | Finds non-terminals unreachable from start symbol |
| `ASTNode` | Generic AST node (node_type, children, token, line, column) |
| `ParserGenerator` | Compiles a Grammar into a recursive-descent parser class |
| `GeneratedParser` | Base class for generated parsers (tokenize + parse) |
| `GrammarDashboard` | ASCII dashboard rendering |

### Data Flow

```
BNF text -> GrammarParser -> Grammar
                               |
                    +----------+----------+
                    |          |          |
              FirstFollow  LeftRec  Ambiguity
              Computer    Detector  Analyzer
                    |
              LL1Classifier
                    |
              ParserGenerator -> GeneratedParser class
                                      |
                               input text -> ASTNode tree
```

## 3. BNF/EBNF Specification Format

```
program       ::= { statement } ;
statement     ::= rule_def | query | assignment ;
rule_def      ::= "RULE" IDENTIFIER ":" condition "->" label ";" ;
condition     ::= "divisible_by" "(" NUMBER ")" | condition "AND" condition | condition "OR" condition ;
label         ::= STRING ;
query         ::= "EVALUATE" expression ;
expression    ::= NUMBER | IDENTIFIER | expression "+" expression ;
assignment    ::= "LET" IDENTIFIER "=" expression ";" ;
```

Terminals: quoted strings, ALL_CAPS token names (IDENTIFIER, NUMBER, STRING).
Non-terminals: lowercase identifiers.
EBNF: `{ }` = zero-or-more, `[ ]` = optional, `( )` = grouping.

## 4. FIRST/FOLLOW Set Computation

- Standard fixed-point algorithm.
- Handle nullable (epsilon) productions.
- FIRST(alpha) for arbitrary symbol sequences.
- FOLLOW adds `$` (EOF) to start symbol's FOLLOW set.
- Iterate until no set changes.

## 5. LL(1) Classification

For each non-terminal with multiple alternatives:
- FIRST sets of alternatives must be pairwise disjoint.
- If any alternative is nullable, its FIRST set must be disjoint with the non-terminal's FOLLOW set.
- Report conflicting productions on failure.

## 6. Left Recursion Detection

- Direct: `A ::= A alpha`
- Indirect: DFS from each non-terminal following first symbols of productions.
- Report the cycle path.

## 7. Ambiguity Analysis

- Bounded breadth-first derivation (max depth configurable, default 6).
- For each non-terminal with multiple alternatives, attempt to find an input string derivable from two different alternatives.
- Report the ambiguous string and the two derivation paths.

## 8. Parser Generator

- For each non-terminal, generate a parse method.
- LL(1) grammars use FIRST-set-based lookahead to select alternatives.
- Non-LL(1) grammars fall back to ordered-choice (PEG-style).
- Tokenizer: longest-match, keywords before identifiers.
- Error reporting: line/column, expected tokens from FIRST/FOLLOW.
- Error recovery: skip to synchronization tokens (`;`, `)`) on syntax error.
- Output: a `GeneratedParser` subclass with `parse()` entry point returning `ASTNode`.

## 9. Built-in Grammar

Ship a FizzBuzz Classification grammar (~8 productions) as a constant in the module. Used by `--grammar-analyze` when no grammar file is specified.

## 10. Dashboard

ASCII box-drawing dashboard showing:
- Grammar inventory: name, terminal count, non-terminal count, production count, LL class
- FIRST/FOLLOW set tables (abbreviated)
- Diagnostics: left recursion, ambiguities, unreachable symbols
- Grammar Health Index: percentage of diagnostics passing

## 11. Exceptions (in `exceptions.py`)

| Exception | Code | Trigger |
|-----------|------|---------|
| `GrammarError` | EFP-GR00 | Base for all grammar errors |
| `GrammarSyntaxError` | EFP-GR01 | Malformed BNF/EBNF specification |
| `GrammarConflictError` | EFP-GR02 | LL(1) conflict detected |
| `GrammarParseError` | EFP-GR03 | Generated parser encounters syntax error in input |

## 12. Configuration (`config.yaml`)

```yaml
grammar:
  enabled: false
  dashboard:
    width: 60
```

Config properties: `grammar_enabled`, `grammar_dashboard_width`.

## 13. CLI Flags (`__main__.py`)

| Flag | Type | Effect |
|------|------|--------|
| `--grammar` | store_true | Enable FizzGrammar: parse, analyze, and generate parser for the built-in FizzBuzz Classification grammar |
| `--grammar-analyze` | store_true | Run full grammar analysis (FIRST/FOLLOW, LL(1), left recursion, ambiguity) and print report |
| `--grammar-dashboard` | store_true | Display the FizzGrammar ASCII dashboard |

## 14. Tests (`tests/test_formal_grammar.py`)

~50 tests covering:
- BNF/EBNF parsing (valid grammars, syntax errors)
- FIRST set computation (basic, nullable, recursive)
- FOLLOW set computation (basic, EOF propagation)
- LL(1) classification (positive and negative cases)
- Left recursion detection (direct, indirect, none)
- Ambiguity detection (ambiguous grammar, clean grammar)
- Unreachable symbol detection
- Parser generation and parsing valid/invalid inputs
- AST node construction
- Error recovery in generated parsers
- Dashboard rendering
- Exception hierarchy

## 15. Integration Points

- `__main__.py`: import, CLI args, setup block, dashboard block.
- `config.py`: 2 properties (`grammar_enabled`, `grammar_dashboard_width`).
- `exceptions.py`: 4 exception classes appended.
- No middleware integration (grammar analysis is a standalone tool, not a per-evaluation middleware).

## 16. Implementation Order

1. Exceptions in `exceptions.py`
2. Core module `formal_grammar.py` (all classes)
3. Config properties in `config.py`
4. Config section in `config.yaml`
5. CLI integration in `__main__.py`
6. Tests in `tests/test_formal_grammar.py`

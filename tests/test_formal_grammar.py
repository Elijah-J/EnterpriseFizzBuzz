"""
Tests for FizzGrammar: Formal Grammar & Parser Generator.

Validates BNF/EBNF parsing, FIRST/FOLLOW set computation, LL(1)
classification, left-recursion detection, ambiguity analysis,
parser generation, AST construction, and dashboard rendering.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.formal_grammar import (
    EPSILON,
    EOF,
    ASTNode,
    AmbiguityAnalyzer,
    FirstFollowComputer,
    Grammar,
    GrammarAnalyzer,
    GrammarDashboard,
    GrammarParser,
    GeneratedParser,
    LL1Classifier,
    LeftRecursionDetector,
    ParserGenerator,
    Production,
    Symbol,
    SymbolKind,
    Token,
    UnreachableSymbolDetector,
    epsilon,
    load_builtin_grammar,
    non_terminal,
    terminal,
)
from enterprise_fizzbuzz.domain.exceptions import (
    GrammarConflictError,
    GrammarError,
    GrammarParseError,
    GrammarSyntaxError,
)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# ============================================================
# Symbol tests
# ============================================================


class TestSymbols:
    """Tests for grammar symbol construction."""

    def test_terminal_creation(self):
        t = terminal("KEYWORD")
        assert t.is_terminal
        assert not t.is_non_terminal
        assert t.name == "KEYWORD"

    def test_non_terminal_creation(self):
        nt = non_terminal("expr")
        assert nt.is_non_terminal
        assert not nt.is_terminal
        assert nt.name == "expr"

    def test_epsilon_creation(self):
        e = epsilon()
        assert e.is_epsilon
        assert not e.is_terminal
        assert e.name == EPSILON

    def test_symbol_equality(self):
        a = terminal("x")
        b = terminal("x")
        assert a == b

    def test_symbol_hashable(self):
        s = {terminal("a"), terminal("b"), terminal("a")}
        assert len(s) == 2


# ============================================================
# Production tests
# ============================================================


class TestProduction:
    """Tests for production rule construction."""

    def test_basic_production(self):
        p = Production(
            lhs=non_terminal("S"),
            rhs=[terminal("a"), non_terminal("B")],
        )
        assert p.lhs.name == "S"
        assert len(p.rhs) == 2
        assert not p.is_epsilon

    def test_epsilon_production(self):
        p = Production(lhs=non_terminal("S"), rhs=[])
        assert p.is_epsilon

    def test_epsilon_symbol_production(self):
        p = Production(lhs=non_terminal("S"), rhs=[epsilon()])
        assert p.is_epsilon

    def test_production_repr(self):
        p = Production(
            lhs=non_terminal("S"),
            rhs=[terminal("a")],
        )
        assert "S" in repr(p)
        assert "a" in repr(p)


# ============================================================
# Grammar tests
# ============================================================


class TestGrammar:
    """Tests for the Grammar container."""

    def test_empty_grammar(self):
        g = Grammar(name="empty")
        assert g.non_terminals == set()
        assert g.terminals == set()
        assert len(g.productions) == 0

    def test_add_production(self):
        g = Grammar(name="test")
        g.add_production(Production(
            lhs=non_terminal("S"),
            rhs=[terminal("a"), non_terminal("B")],
        ))
        assert "S" in g.non_terminals
        assert "a" in g.terminals
        assert len(g.productions) == 1

    def test_productions_for(self):
        g = Grammar(name="test")
        g.add_production(Production(lhs=non_terminal("S"), rhs=[terminal("a")]))
        g.add_production(Production(lhs=non_terminal("S"), rhs=[terminal("b")]))
        g.add_production(Production(lhs=non_terminal("T"), rhs=[terminal("c")]))
        assert len(g.productions_for("S")) == 2
        assert len(g.productions_for("T")) == 1
        assert len(g.productions_for("Z")) == 0

    def test_statistics(self):
        g = Grammar(name="stats_test", start_symbol=non_terminal("S"))
        g.add_production(Production(lhs=non_terminal("S"), rhs=[terminal("x")]))
        stats = g.statistics()
        assert stats["name"] == "stats_test"
        assert stats["terminals"] == 1
        assert stats["non_terminals"] == 1
        assert stats["productions"] == 1


# ============================================================
# GrammarParser (BNF/EBNF) tests
# ============================================================


class TestGrammarParser:
    """Tests for parsing BNF/EBNF specifications."""

    def test_simple_grammar(self):
        text = 'S ::= "a" ;'
        g = GrammarParser().parse(text, name="simple")
        assert len(g.productions) == 1
        assert g.start_symbol is not None
        assert g.start_symbol.name == "S"

    def test_alternatives(self):
        text = 'S ::= "a" | "b" | "c" ;'
        g = GrammarParser().parse(text)
        assert len(g.productions) == 3

    def test_multiple_rules(self):
        text = '''
        s ::= a "x" ;
        a ::= "a" | "b" ;
        '''
        g = GrammarParser().parse(text)
        assert len(g.productions) == 3
        assert "s" in g.non_terminals
        assert "a" in g.non_terminals

    def test_uppercase_terminals(self):
        text = 'S ::= NUMBER "+" NUMBER ;'
        g = GrammarParser().parse(text)
        assert "NUMBER" in g.terminals
        assert "+" in g.terminals

    def test_ebnf_braces(self):
        text = 'S ::= { "a" } ;'
        g = GrammarParser().parse(text)
        assert len(g.productions) == 1

    def test_ebnf_brackets(self):
        text = 'S ::= [ "a" ] "b" ;'
        g = GrammarParser().parse(text)
        assert len(g.productions) == 1

    def test_syntax_error_missing_derives(self):
        text = 'S "a" ;'
        with pytest.raises(GrammarSyntaxError):
            GrammarParser().parse(text)

    def test_syntax_error_missing_semicolon(self):
        text = 'S ::= "a"'
        with pytest.raises(GrammarSyntaxError):
            GrammarParser().parse(text)

    def test_comments_ignored(self):
        text = '''
        # This is a comment
        S ::= "a" ;  # inline comment
        '''
        g = GrammarParser().parse(text)
        assert len(g.productions) == 1

    def test_builtin_grammar_parses(self):
        g = load_builtin_grammar()
        assert g.name == "FizzBuzz Classification"
        assert len(g.productions) > 0
        assert g.start_symbol is not None


# ============================================================
# FIRST / FOLLOW computation tests
# ============================================================


class TestFirstFollowComputer:
    """Tests for FIRST and FOLLOW set computation."""

    def _make_grammar(self, text: str) -> Grammar:
        return GrammarParser().parse(text)

    def test_first_single_terminal(self):
        g = self._make_grammar('S ::= "a" ;')
        ff = FirstFollowComputer(g)
        assert "a" in ff.first_of("S")

    def test_first_multiple_alternatives(self):
        g = self._make_grammar('S ::= "a" | "b" ;')
        ff = FirstFollowComputer(g)
        assert "a" in ff.first_of("S")
        assert "b" in ff.first_of("S")

    def test_first_through_non_terminal(self):
        g = self._make_grammar('''
        s ::= a ;
        a ::= "x" ;
        ''')
        ff = FirstFollowComputer(g)
        assert "x" in ff.first_of("s")

    def test_nullable_detection(self):
        g = Grammar(name="nullable_test", start_symbol=non_terminal("S"))
        g.add_production(Production(lhs=non_terminal("S"), rhs=[non_terminal("A"), terminal("b")]))
        g.add_production(Production(lhs=non_terminal("A"), rhs=[]))
        ff = FirstFollowComputer(g)
        assert "A" in ff.nullable

    def test_first_with_nullable(self):
        g = Grammar(name="nullable_first", start_symbol=non_terminal("S"))
        g.add_production(Production(lhs=non_terminal("S"), rhs=[non_terminal("A"), terminal("b")]))
        g.add_production(Production(lhs=non_terminal("A"), rhs=[terminal("a")]))
        g.add_production(Production(lhs=non_terminal("A"), rhs=[]))
        ff = FirstFollowComputer(g)
        first_s = ff.first_of("S")
        assert "a" in first_s
        assert "b" in first_s

    def test_follow_start_has_eof(self):
        g = self._make_grammar('S ::= "a" ;')
        ff = FirstFollowComputer(g)
        assert EOF in ff.follow_of("S")

    def test_follow_propagation(self):
        g = self._make_grammar('''
        s ::= a "b" ;
        a ::= "a" ;
        ''')
        ff = FirstFollowComputer(g)
        assert "b" in ff.follow_of("a")

    def test_first_of_terminal(self):
        g = self._make_grammar('S ::= "a" ;')
        ff = FirstFollowComputer(g)
        assert ff.first_of("a") == {"a"}


# ============================================================
# LL(1) classification tests
# ============================================================


class TestLL1Classifier:
    """Tests for LL(1) grammar classification."""

    def test_ll1_grammar(self):
        g = GrammarParser().parse('''
        s ::= "a" aa | "b" bb ;
        aa ::= "x" ;
        bb ::= "y" ;
        ''')
        ff = FirstFollowComputer(g)
        cl = LL1Classifier(g, ff)
        assert cl.is_ll1
        assert len(cl.conflicts) == 0

    def test_non_ll1_grammar(self):
        g = GrammarParser().parse('''
        s ::= "a" aa | "a" bb ;
        aa ::= "x" ;
        bb ::= "y" ;
        ''')
        ff = FirstFollowComputer(g)
        cl = LL1Classifier(g, ff)
        assert not cl.is_ll1
        assert len(cl.conflicts) > 0

    def test_single_alternative_always_ll1(self):
        g = GrammarParser().parse('S ::= "a" "b" "c" ;')
        ff = FirstFollowComputer(g)
        cl = LL1Classifier(g, ff)
        assert cl.is_ll1


# ============================================================
# Left recursion detection tests
# ============================================================


class TestLeftRecursionDetector:
    """Tests for left recursion detection."""

    def test_no_left_recursion(self):
        g = GrammarParser().parse('''
        S ::= "a" S | "b" ;
        ''')
        lr = LeftRecursionDetector(g)
        assert not lr.has_left_recursion

    def test_direct_left_recursion(self):
        g = Grammar(name="lr", start_symbol=non_terminal("E"))
        g.add_production(Production(
            lhs=non_terminal("E"),
            rhs=[non_terminal("E"), terminal("+"), non_terminal("T")],
        ))
        g.add_production(Production(
            lhs=non_terminal("E"),
            rhs=[non_terminal("T")],
        ))
        g.add_production(Production(
            lhs=non_terminal("T"),
            rhs=[terminal("id")],
        ))
        lr = LeftRecursionDetector(g)
        assert lr.has_left_recursion
        assert any("E" in cycle for cycle in lr.cycles)

    def test_indirect_left_recursion(self):
        g = Grammar(name="indirect_lr", start_symbol=non_terminal("A"))
        g.add_production(Production(lhs=non_terminal("A"), rhs=[non_terminal("B"), terminal("a")]))
        g.add_production(Production(lhs=non_terminal("B"), rhs=[non_terminal("A"), terminal("b")]))
        g.add_production(Production(lhs=non_terminal("B"), rhs=[terminal("c")]))
        lr = LeftRecursionDetector(g)
        assert lr.has_left_recursion


# ============================================================
# Ambiguity analysis tests
# ============================================================


class TestAmbiguityAnalyzer:
    """Tests for bounded ambiguity analysis."""

    def test_unambiguous_grammar(self):
        g = GrammarParser().parse('''
        S ::= "a" | "b" ;
        ''')
        aa = AmbiguityAnalyzer(g, max_depth=4)
        assert not aa.is_ambiguous

    def test_ambiguous_grammar(self):
        g = Grammar(name="ambiguous", start_symbol=non_terminal("S"))
        g.add_production(Production(lhs=non_terminal("S"), rhs=[terminal("a")]))
        g.add_production(Production(lhs=non_terminal("S"), rhs=[terminal("a")]))
        aa = AmbiguityAnalyzer(g, max_depth=4)
        assert aa.is_ambiguous
        assert len(aa.ambiguities) > 0
        assert aa.ambiguities[0]["ambiguous_string"] == "a"


# ============================================================
# Unreachable symbol detection tests
# ============================================================


class TestUnreachableSymbolDetector:
    """Tests for unreachable symbol detection."""

    def test_all_reachable(self):
        g = GrammarParser().parse('''
        s ::= a ;
        a ::= "a" ;
        ''')
        usd = UnreachableSymbolDetector(g)
        assert len(usd.unreachable) == 0

    def test_unreachable_non_terminal(self):
        g = GrammarParser().parse('''
        s ::= "a" ;
        b ::= "b" ;
        ''')
        usd = UnreachableSymbolDetector(g)
        assert "b" in usd.unreachable

    def test_no_start_symbol(self):
        g = Grammar(name="no_start")
        g.add_production(Production(lhs=non_terminal("A"), rhs=[terminal("x")]))
        usd = UnreachableSymbolDetector(g)
        assert "A" in usd.unreachable


# ============================================================
# AST Node tests
# ============================================================


class TestASTNode:
    """Tests for the generic AST node."""

    def test_leaf_node(self):
        node = ASTNode(node_type="NUMBER", token="42", line=1, column=5)
        assert node.is_leaf()
        assert node.token == "42"

    def test_interior_node(self):
        child = ASTNode(node_type="NUM", token="1")
        parent = ASTNode(node_type="expr", children=[child])
        assert not parent.is_leaf()
        assert len(parent.children) == 1

    def test_pretty_print(self):
        child = ASTNode(node_type="NUM", token="42")
        parent = ASTNode(node_type="expr", children=[child])
        text = parent.pretty()
        assert "expr" in text
        assert "42" in text

    def test_repr_leaf(self):
        node = ASTNode(node_type="X", token="v")
        assert "token=" in repr(node)

    def test_repr_interior(self):
        node = ASTNode(node_type="X", children=[ASTNode(node_type="Y", token="z")])
        assert "children=1" in repr(node)


# ============================================================
# Parser Generator tests
# ============================================================


class TestParserGenerator:
    """Tests for the parser generator and generated parsers."""

    def test_generate_parser(self):
        g = GrammarParser().parse('''
        S ::= "hello" ;
        ''')
        gen = ParserGenerator(g)
        parser = gen.generate()
        assert isinstance(parser, GeneratedParser)
        assert parser._grammar is not None

    def test_parse_simple_input(self):
        g = GrammarParser().parse('''
        S ::= "hello" "world" ;
        ''')
        gen = ParserGenerator(g)
        parser = gen.generate()
        result = parser.parse("hello world")
        assert result.node_type == "S"
        assert len(result.children) == 2

    def test_parse_with_alternatives(self):
        g = GrammarParser().parse('''
        S ::= "a" | "b" ;
        ''')
        gen = ParserGenerator(g)
        parser = gen.generate()
        result = parser.parse("a")
        assert result.node_type == "S"

    def test_parse_with_non_terminals(self):
        g = GrammarParser().parse('''
        S ::= greeting name ;
        greeting ::= "hello" ;
        name ::= "world" ;
        ''')
        gen = ParserGenerator(g)
        parser = gen.generate()
        result = parser.parse("hello world")
        assert result.node_type == "S"
        assert len(result.children) == 2
        assert result.children[0].node_type == "greeting"
        assert result.children[1].node_type == "name"

    def test_parse_error_reporting(self):
        g = GrammarParser().parse('''
        S ::= "a" "b" ;
        ''')
        gen = ParserGenerator(g)
        parser = gen.generate()
        parser.parse("a c")
        assert len(parser._errors) > 0

    def test_builtin_grammar_generates(self):
        g = load_builtin_grammar()
        gen = ParserGenerator(g)
        parser = gen.generate()
        assert parser._grammar is not None
        assert parser._first_sets is not None
        assert parser._follow_sets is not None


# ============================================================
# Grammar Analyzer tests
# ============================================================


class TestGrammarAnalyzer:
    """Tests for the combined grammar analyzer."""

    def test_analyzer_report_keys(self):
        g = GrammarParser().parse('''
        S ::= "a" | "b" ;
        ''')
        analyzer = GrammarAnalyzer(g)
        report = analyzer.report()
        assert "statistics" in report
        assert "first_sets" in report
        assert "follow_sets" in report
        assert "is_ll1" in report
        assert "left_recursion" in report
        assert "ambiguity" in report
        assert "unreachable_symbols" in report
        assert "health_index" in report
        assert "grammar_class" in report

    def test_clean_grammar_health(self):
        g = GrammarParser().parse('''
        S ::= "a" | "b" ;
        ''')
        analyzer = GrammarAnalyzer(g)
        report = analyzer.report()
        assert report["health_index"] == 100.0
        assert report["grammar_class"] == "LL(1)"

    def test_text_report_renders(self):
        g = GrammarParser().parse('''
        s ::= aa "x" ;
        aa ::= "a" | "b" ;
        ''')
        analyzer = GrammarAnalyzer(g)
        text = analyzer.render_text_report()
        assert "FIRST sets" in text
        assert "FOLLOW sets" in text
        assert "Left recursion" in text

    def test_builtin_grammar_analysis(self):
        g = load_builtin_grammar()
        analyzer = GrammarAnalyzer(g)
        report = analyzer.report()
        assert report["statistics"]["name"] == "FizzBuzz Classification"
        assert report["statistics"]["productions"] > 0


# ============================================================
# Dashboard tests
# ============================================================


class TestGrammarDashboard:
    """Tests for the ASCII dashboard rendering."""

    def test_dashboard_renders(self):
        g = GrammarParser().parse('''
        S ::= "a" | "b" ;
        ''')
        output = GrammarDashboard.render(g)
        assert "FizzGrammar" in output
        assert "GRAMMAR INVENTORY" in output
        assert "FIRST SETS" in output
        assert "FOLLOW SETS" in output
        assert "DIAGNOSTICS" in output
        assert "HEALTH" in output

    def test_dashboard_custom_width(self):
        g = GrammarParser().parse('S ::= "a" ;')
        output = GrammarDashboard.render(g, width=80)
        # Check that borders are 80 chars wide
        first_line = output.split("\n")[0]
        assert len(first_line) == 80

    def test_dashboard_with_analyzer(self):
        g = load_builtin_grammar()
        analyzer = GrammarAnalyzer(g)
        output = GrammarDashboard.render(g, analyzer=analyzer)
        assert "FizzBuzz Classification" in output

    def test_dashboard_shows_conflicts(self):
        g = GrammarParser().parse('''
        s ::= "a" aa | "a" bb ;
        aa ::= "x" ;
        bb ::= "y" ;
        ''')
        output = GrammarDashboard.render(g)
        assert "NO" in output  # LL(1): NO


# ============================================================
# Exception tests
# ============================================================


class TestExceptions:
    """Tests for grammar exception hierarchy."""

    def test_grammar_error_base(self):
        e = GrammarError("test error")
        assert "EFP-GR00" in str(e)

    def test_grammar_syntax_error(self):
        e = GrammarSyntaxError(10, 5, "unexpected token")
        assert e.line == 10
        assert e.column == 5
        assert "EFP-GR01" in str(e)
        assert "unexpected token" in str(e)

    def test_grammar_conflict_error(self):
        e = GrammarConflictError("expr", ["prod1", "prod2"])
        assert e.non_terminal == "expr"
        assert "EFP-GR02" in str(e)

    def test_grammar_parse_error(self):
        e = GrammarParseError(3, 7, "KEYWORD", ["NUMBER", "IDENTIFIER"])
        assert e.line == 3
        assert e.column == 7
        assert e.found == "KEYWORD"
        assert "EFP-GR03" in str(e)

    def test_exceptions_inherit_from_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(GrammarError, FizzBuzzError)
        assert issubclass(GrammarSyntaxError, GrammarError)
        assert issubclass(GrammarConflictError, GrammarError)
        assert issubclass(GrammarParseError, GrammarError)


# ============================================================
# Integration tests
# ============================================================


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_pipeline_builtin_grammar(self):
        """Load builtin grammar -> analyze -> generate parser -> dashboard."""
        g = load_builtin_grammar()
        analyzer = GrammarAnalyzer(g)
        report = analyzer.report()
        assert report["statistics"]["productions"] > 0

        gen = ParserGenerator(g)
        parser = gen.generate()
        assert parser._grammar is not None

        dashboard = GrammarDashboard.render(g, analyzer=analyzer)
        assert len(dashboard) > 100

    def test_custom_grammar_roundtrip(self):
        """Define grammar in BNF -> parse -> analyze -> generate parser -> parse input."""
        bnf = '''
        greeting ::= "hello" name ;
        name ::= "world" | "fizzbuzz" ;
        '''
        g = GrammarParser().parse(bnf, name="greeting")
        analyzer = GrammarAnalyzer(g)
        assert analyzer.classifier.is_ll1

        gen = ParserGenerator(g)
        parser = gen.generate()
        result = parser.parse("hello world")
        assert result.node_type == "greeting"
        assert result.children[1].node_type == "name"

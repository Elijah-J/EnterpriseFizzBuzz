"""
Enterprise FizzBuzz Platform - FizzRegex Engine Test Suite

Comprehensive test coverage for the regular expression engine, validating
Thompson's NFA construction, Rabin-Scott DFA compilation, Hopcroft DFA
minimization, and the O(n) matching guarantee.

The tests are organized by compilation pipeline phase:
1. AST parsing and construction
2. NFA generation via Thompson's algorithm
3. DFA compilation via Rabin-Scott subset construction
4. DFA minimization via Hopcroft's partition refinement
5. Full-match and search operations
6. FizzBuzz classification patterns
7. Pathological pattern performance
8. Middleware integration
9. Dashboard rendering
"""

from __future__ import annotations

import time

import pytest

from enterprise_fizzbuzz.infrastructure.regex_engine import (
    ASTNodeType,
    BenchmarkResult,
    CompilationStats,
    DFA,
    DFAMinimizer,
    DFAState,
    FizzBuzzPatterns,
    MatchResult,
    Matcher,
    NFA,
    NFAState,
    RegexAST,
    RegexBenchmark,
    RegexCompiler,
    RegexDashboard,
    RegexMiddleware,
    RegexParser,
    SubsetConstructor,
    ThompsonConstructor,
    _char_matches,
    _reset_nfa_counter,
)
from enterprise_fizzbuzz.domain.exceptions import (
    RegexCompilationError,
    RegexEngineError,
    RegexPatternSyntaxError,
)


# ============================================================
# Parser Tests
# ============================================================


class TestRegexParser:
    """Tests for the recursive-descent regex parser."""

    def test_empty_pattern(self):
        ast = RegexParser("").parse()
        assert ast.node_type == ASTNodeType.EMPTY

    def test_single_literal(self):
        ast = RegexParser("a").parse()
        assert ast.node_type == ASTNodeType.LITERAL
        assert ast.value == "a"

    def test_concatenation(self):
        ast = RegexParser("ab").parse()
        assert ast.node_type == ASTNodeType.CONCAT
        assert len(ast.children) == 2
        assert ast.children[0].value == "a"
        assert ast.children[1].value == "b"

    def test_three_way_concatenation(self):
        ast = RegexParser("abc").parse()
        assert ast.node_type == ASTNodeType.CONCAT
        assert len(ast.children) == 3

    def test_alternation(self):
        ast = RegexParser("a|b").parse()
        assert ast.node_type == ASTNodeType.ALTERNATION
        assert len(ast.children) == 2
        assert ast.children[0].value == "a"
        assert ast.children[1].value == "b"

    def test_three_way_alternation(self):
        ast = RegexParser("a|b|c").parse()
        assert ast.node_type == ASTNodeType.ALTERNATION
        assert len(ast.children) == 3

    def test_kleene_star(self):
        ast = RegexParser("a*").parse()
        assert ast.node_type == ASTNodeType.KLEENE_STAR
        assert ast.children[0].value == "a"

    def test_plus(self):
        ast = RegexParser("a+").parse()
        assert ast.node_type == ASTNodeType.PLUS
        assert ast.children[0].value == "a"

    def test_optional(self):
        ast = RegexParser("a?").parse()
        assert ast.node_type == ASTNodeType.OPTIONAL
        assert ast.children[0].value == "a"

    def test_dot(self):
        ast = RegexParser(".").parse()
        assert ast.node_type == ASTNodeType.DOT

    def test_anchor_start(self):
        ast = RegexParser("^a").parse()
        assert ast.node_type == ASTNodeType.CONCAT
        assert ast.children[0].node_type == ASTNodeType.ANCHOR_START

    def test_anchor_end(self):
        ast = RegexParser("a$").parse()
        assert ast.node_type == ASTNodeType.CONCAT
        assert ast.children[1].node_type == ASTNodeType.ANCHOR_END

    def test_parenthesized_group(self):
        ast = RegexParser("(ab)").parse()
        assert ast.node_type == ASTNodeType.CONCAT
        assert ast.children[0].value == "a"

    def test_nested_groups(self):
        ast = RegexParser("(a(b))").parse()
        assert ast.node_type == ASTNodeType.CONCAT

    def test_alternation_in_group(self):
        ast = RegexParser("(a|b)c").parse()
        assert ast.node_type == ASTNodeType.CONCAT
        assert ast.children[0].node_type == ASTNodeType.ALTERNATION

    def test_char_class_single(self):
        ast = RegexParser("[a]").parse()
        assert ast.node_type == ASTNodeType.CHAR_CLASS
        assert ast.char_ranges == [("a", "a")]

    def test_char_class_range(self):
        ast = RegexParser("[a-z]").parse()
        assert ast.node_type == ASTNodeType.CHAR_CLASS
        assert ast.char_ranges == [("a", "z")]

    def test_char_class_negated(self):
        ast = RegexParser("[^0-9]").parse()
        assert ast.node_type == ASTNodeType.CHAR_CLASS
        assert ast.negated is True

    def test_char_class_multiple_ranges(self):
        ast = RegexParser("[a-zA-Z]").parse()
        assert ast.node_type == ASTNodeType.CHAR_CLASS
        assert len(ast.char_ranges) == 2

    def test_escape_digit(self):
        ast = RegexParser("\\d").parse()
        assert ast.node_type == ASTNodeType.CHAR_CLASS
        assert ast.char_ranges == [("0", "9")]

    def test_escape_word(self):
        ast = RegexParser("\\w").parse()
        assert ast.node_type == ASTNodeType.CHAR_CLASS

    def test_escape_whitespace(self):
        ast = RegexParser("\\s").parse()
        assert ast.node_type == ASTNodeType.CHAR_CLASS

    def test_escape_literal(self):
        ast = RegexParser("\\*").parse()
        assert ast.node_type == ASTNodeType.LITERAL
        assert ast.value == "*"

    def test_escape_backslash(self):
        ast = RegexParser("\\\\").parse()
        assert ast.node_type == ASTNodeType.LITERAL
        assert ast.value == "\\"

    def test_negated_digit(self):
        ast = RegexParser("\\D").parse()
        assert ast.node_type == ASTNodeType.CHAR_CLASS
        assert ast.negated is True

    def test_negated_word(self):
        ast = RegexParser("\\W").parse()
        assert ast.negated is True

    def test_negated_whitespace(self):
        ast = RegexParser("\\S").parse()
        assert ast.negated is True

    def test_missing_closing_paren_raises(self):
        with pytest.raises(RegexPatternSyntaxError):
            RegexParser("(ab").parse()

    def test_trailing_backslash_raises(self):
        with pytest.raises(RegexPatternSyntaxError):
            RegexParser("a\\").parse()

    def test_missing_closing_bracket_raises(self):
        with pytest.raises(RegexPatternSyntaxError):
            RegexParser("[abc").parse()

    def test_complex_pattern(self):
        ast = RegexParser("(Fizz|Buzz|FizzBuzz)").parse()
        assert ast.node_type == ASTNodeType.ALTERNATION
        assert len(ast.children) == 3

    def test_quantifier_on_group(self):
        ast = RegexParser("(ab)*").parse()
        assert ast.node_type == ASTNodeType.KLEENE_STAR

    def test_ast_repr_literal(self):
        ast = RegexAST(node_type=ASTNodeType.LITERAL, value="x")
        assert "Lit" in repr(ast)

    def test_ast_repr_dot(self):
        ast = RegexAST(node_type=ASTNodeType.DOT)
        assert "Dot" in repr(ast)


# ============================================================
# NFA Tests — Thompson's Construction
# ============================================================


class TestThompsonNFA:
    """Tests for Thompson's NFA construction algorithm."""

    def setup_method(self):
        self.thompson = ThompsonConstructor()

    def test_literal_creates_two_states(self):
        ast = RegexAST(node_type=ASTNodeType.LITERAL, value="a")
        nfa = self.thompson.build(ast)
        assert nfa.state_count() == 2
        assert nfa.start.accepting is False
        assert nfa.accept.accepting is True

    def test_literal_transition(self):
        ast = RegexAST(node_type=ASTNodeType.LITERAL, value="a")
        nfa = self.thompson.build(ast)
        assert "a" in nfa.start.transitions
        assert nfa.accept in nfa.start.transitions["a"]

    def test_concat_chains_fragments(self):
        ast = RegexAST(
            node_type=ASTNodeType.CONCAT,
            children=[
                RegexAST(node_type=ASTNodeType.LITERAL, value="a"),
                RegexAST(node_type=ASTNodeType.LITERAL, value="b"),
            ],
        )
        nfa = self.thompson.build(ast)
        assert nfa.state_count() == 4

    def test_alternation_creates_branch(self):
        ast = RegexAST(
            node_type=ASTNodeType.ALTERNATION,
            children=[
                RegexAST(node_type=ASTNodeType.LITERAL, value="a"),
                RegexAST(node_type=ASTNodeType.LITERAL, value="b"),
            ],
        )
        nfa = self.thompson.build(ast)
        # start + 2 branches (2 states each) + accept = 6
        assert nfa.state_count() == 6
        assert len(nfa.start.epsilon_transitions) == 2

    def test_kleene_star_has_epsilon_loop(self):
        ast = RegexAST(
            node_type=ASTNodeType.KLEENE_STAR,
            children=[RegexAST(node_type=ASTNodeType.LITERAL, value="a")],
        )
        nfa = self.thompson.build(ast)
        # Can accept empty string (epsilon from start to accept)
        assert any(
            eps.accepting or eps == nfa.accept
            for eps in nfa.start.epsilon_transitions
        )

    def test_plus_requires_at_least_one(self):
        ast = RegexAST(
            node_type=ASTNodeType.PLUS,
            children=[RegexAST(node_type=ASTNodeType.LITERAL, value="a")],
        )
        nfa = self.thompson.build(ast)
        # start should NOT have direct epsilon to accept
        direct_to_accept = nfa.accept in nfa.start.epsilon_transitions
        assert not direct_to_accept

    def test_optional_accepts_empty(self):
        ast = RegexAST(
            node_type=ASTNodeType.OPTIONAL,
            children=[RegexAST(node_type=ASTNodeType.LITERAL, value="a")],
        )
        nfa = self.thompson.build(ast)
        assert nfa.accept in nfa.start.epsilon_transitions

    def test_empty_produces_epsilon_nfa(self):
        ast = RegexAST(node_type=ASTNodeType.EMPTY)
        nfa = self.thompson.build(ast)
        assert nfa.state_count() == 2
        assert nfa.accept in nfa.start.epsilon_transitions

    def test_dot_transitions_cover_printable(self):
        ast = RegexAST(node_type=ASTNodeType.DOT)
        nfa = self.thompson.build(ast)
        assert "a" in nfa.start.transitions
        assert "Z" in nfa.start.transitions
        assert "5" in nfa.start.transitions

    def test_char_class_transitions(self):
        ast = RegexAST(
            node_type=ASTNodeType.CHAR_CLASS,
            char_ranges=[("0", "9")],
        )
        nfa = self.thompson.build(ast)
        assert "0" in nfa.start.transitions
        assert "9" in nfa.start.transitions
        assert "a" not in nfa.start.transitions

    def test_negated_char_class(self):
        ast = RegexAST(
            node_type=ASTNodeType.CHAR_CLASS,
            char_ranges=[("0", "9")],
            negated=True,
        )
        nfa = self.thompson.build(ast)
        assert "a" in nfa.start.transitions
        assert "0" not in nfa.start.transitions

    def test_nfa_all_states(self):
        ast = RegexAST(node_type=ASTNodeType.LITERAL, value="a")
        nfa = self.thompson.build(ast)
        states = nfa.all_states()
        assert len(states) == 2

    def test_nfa_state_hash_and_equality(self):
        s1 = NFAState(state_id=42)
        s2 = NFAState(state_id=42)
        assert s1 == s2
        assert hash(s1) == hash(s2)
        assert s1 != "not a state"


# ============================================================
# DFA Tests — Rabin-Scott Subset Construction
# ============================================================


class TestSubsetConstruction:
    """Tests for Rabin-Scott DFA compilation."""

    def setup_method(self):
        self.thompson = ThompsonConstructor()

    def _compile_to_dfa(self, pattern: str) -> DFA:
        ast = RegexParser(pattern).parse()
        nfa = self.thompson.build(ast)
        return SubsetConstructor(nfa).build()

    def test_single_literal_dfa(self):
        dfa = self._compile_to_dfa("a")
        assert dfa.state_count() >= 2
        assert len(dfa.accepting_states) >= 1

    def test_alternation_dfa(self):
        dfa = self._compile_to_dfa("a|b")
        assert dfa.state_count() >= 2

    def test_kleene_star_dfa_accepts_empty(self):
        dfa = self._compile_to_dfa("a*")
        # Start state should be accepting (empty string matches)
        assert dfa.start.accepting is True

    def test_concat_dfa(self):
        dfa = self._compile_to_dfa("ab")
        assert dfa.state_count() >= 2

    def test_dfa_has_no_epsilon_transitions(self):
        """DFA states are frozensets; no epsilon transitions remain."""
        dfa = self._compile_to_dfa("a|b*")
        # All transitions go to concrete states (frozensets)
        for trans_map in dfa.transitions.values():
            for target in trans_map.values():
                assert isinstance(target, frozenset)

    def test_dfa_alphabet_extraction(self):
        dfa = self._compile_to_dfa("a|b")
        assert "a" in dfa.alphabet
        assert "b" in dfa.alphabet


# ============================================================
# DFA Minimization Tests — Hopcroft's Algorithm
# ============================================================


class TestDFAMinimizer:
    """Tests for Hopcroft's DFA minimization algorithm."""

    def setup_method(self):
        self.thompson = ThompsonConstructor()
        self.minimizer = DFAMinimizer()

    def _compile_and_minimize(self, pattern: str) -> tuple[DFA, DFA]:
        ast = RegexParser(pattern).parse()
        nfa = self.thompson.build(ast)
        dfa = SubsetConstructor(nfa).build()
        min_dfa = self.minimizer.minimize(dfa)
        return dfa, min_dfa

    def test_minimized_has_fewer_or_equal_states(self):
        dfa, min_dfa = self._compile_and_minimize("a|b")
        assert min_dfa.state_count() <= dfa.state_count()

    def test_minimization_preserves_acceptance(self):
        """After minimization, the DFA must still accept the same language."""
        dfa, min_dfa = self._compile_and_minimize("(a|b)*")
        # Both should have accepting start states
        assert dfa.start.accepting == min_dfa.start.accepting

    def test_minimization_on_complex_pattern(self):
        dfa, min_dfa = self._compile_and_minimize("(a|b|c)(d|e|f)")
        assert min_dfa.state_count() <= dfa.state_count()

    def test_minimized_dfa_is_functional(self):
        """Matching still works after minimization."""
        _, min_dfa = self._compile_and_minimize("ab|ac")
        matcher = Matcher(min_dfa, "ab|ac")
        assert matcher.is_match("ab")
        assert matcher.is_match("ac")
        assert not matcher.is_match("ad")


# ============================================================
# Matcher Tests — O(n) DFA Simulation
# ============================================================


class TestMatcher:
    """Tests for the O(n) DFA-based matcher."""

    def setup_method(self):
        self.compiler = RegexCompiler()

    def _match(self, pattern: str, text: str) -> MatchResult:
        matcher, _ = self.compiler.compile(pattern)
        return matcher.full_match(text)

    def test_exact_match(self):
        assert self._match("hello", "hello").matched is True

    def test_no_match(self):
        assert self._match("hello", "world").matched is False

    def test_alternation_match(self):
        assert self._match("cat|dog", "cat").matched is True
        assert self._match("cat|dog", "dog").matched is True
        assert self._match("cat|dog", "fish").matched is False

    def test_kleene_star_zero(self):
        assert self._match("a*", "").matched is True

    def test_kleene_star_multiple(self):
        assert self._match("a*", "aaa").matched is True

    def test_plus_requires_one(self):
        assert self._match("a+", "").matched is False
        assert self._match("a+", "a").matched is True
        assert self._match("a+", "aaa").matched is True

    def test_optional_with_and_without(self):
        assert self._match("a?", "").matched is True
        assert self._match("a?", "a").matched is True
        assert self._match("a?", "aa").matched is False

    def test_dot_matches_any(self):
        assert self._match(".", "x").matched is True
        assert self._match(".", "5").matched is True
        assert self._match("..", "ab").matched is True

    def test_char_class(self):
        assert self._match("[abc]", "a").matched is True
        assert self._match("[abc]", "d").matched is False

    def test_char_range(self):
        assert self._match("[a-z]", "m").matched is True
        assert self._match("[a-z]", "A").matched is False

    def test_negated_class(self):
        assert self._match("[^0-9]", "a").matched is True
        assert self._match("[^0-9]", "5").matched is False

    def test_digit_shorthand(self):
        assert self._match("\\d", "5").matched is True
        assert self._match("\\d", "a").matched is False

    def test_word_shorthand(self):
        assert self._match("\\w", "a").matched is True
        assert self._match("\\w", "_").matched is True

    def test_escaped_special(self):
        assert self._match("\\.", ".").matched is True
        assert self._match("\\.", "a").matched is False

    def test_complex_pattern(self):
        assert self._match("(ab|cd)*", "").matched is True
        assert self._match("(ab|cd)*", "ab").matched is True
        assert self._match("(ab|cd)*", "abcd").matched is True
        assert self._match("(ab|cd)*", "abab").matched is True

    def test_fizzbuzz_pattern(self):
        assert self._match("Fizz", "Fizz").matched is True
        assert self._match("Buzz", "Buzz").matched is True
        assert self._match("FizzBuzz", "FizzBuzz").matched is True

    def test_fizzbuzz_alternation(self):
        pattern = "Fizz|Buzz|FizzBuzz"
        assert self._match(pattern, "Fizz").matched is True
        assert self._match(pattern, "Buzz").matched is True
        assert self._match(pattern, "FizzBuzz").matched is True
        assert self._match(pattern, "42").matched is False

    def test_number_pattern(self):
        pattern = "(0|1|2|3|4|5|6|7|8|9)+"
        assert self._match(pattern, "42").matched is True
        assert self._match(pattern, "0").matched is True
        assert self._match(pattern, "100").matched is True
        assert self._match(pattern, "").matched is False
        assert self._match(pattern, "abc").matched is False

    def test_match_result_matched_text(self):
        result = self._match("hello", "hello")
        assert result.matched_text == "hello"

    def test_match_result_no_match_text(self):
        result = self._match("hello", "world")
        assert result.matched_text == ""

    def test_search_finds_substring(self):
        matcher, _ = self.compiler.compile("fizz")
        result = matcher.search("this is fizz here")
        assert result.matched is True
        assert result.matched_text == "fizz"

    def test_search_no_match(self):
        matcher, _ = self.compiler.compile("xyz")
        result = matcher.search("hello world")
        assert result.matched is False

    def test_is_match_convenience(self):
        matcher, _ = self.compiler.compile("test")
        assert matcher.is_match("test") is True
        assert matcher.is_match("other") is False


# ============================================================
# Compiler Pipeline Tests
# ============================================================


class TestRegexCompiler:
    """Tests for the full compilation pipeline."""

    def setup_method(self):
        self.compiler = RegexCompiler()

    def test_compile_returns_matcher_and_stats(self):
        matcher, stats = self.compiler.compile("abc")
        assert isinstance(matcher, Matcher)
        assert isinstance(stats, CompilationStats)

    def test_stats_has_state_counts(self):
        _, stats = self.compiler.compile("a|b")
        assert stats.nfa_state_count > 0
        assert stats.dfa_state_count > 0
        assert stats.minimized_state_count > 0

    def test_stats_times_are_nonnegative(self):
        _, stats = self.compiler.compile("(a|b)*c")
        assert stats.parse_time_us >= 0
        assert stats.nfa_time_us >= 0
        assert stats.dfa_time_us >= 0
        assert stats.minimize_time_us >= 0
        assert stats.total_time_us >= 0

    def test_states_eliminated_nonnegative(self):
        _, stats = self.compiler.compile("a|b|c")
        assert stats.states_eliminated >= 0

    def test_pattern_in_stats(self):
        _, stats = self.compiler.compile("test")
        assert stats.pattern == "test"


# ============================================================
# FizzBuzz Patterns Tests
# ============================================================


class TestFizzBuzzPatterns:
    """Tests for pre-compiled FizzBuzz classification patterns."""

    def setup_method(self):
        self.patterns = FizzBuzzPatterns()

    def test_pattern_count(self):
        assert self.patterns.pattern_count == 7

    def test_validate_fizz(self):
        assert self.patterns.validate_classification("Fizz") is True

    def test_validate_buzz(self):
        assert self.patterns.validate_classification("Buzz") is True

    def test_validate_fizzbuzz(self):
        assert self.patterns.validate_classification("FizzBuzz") is True

    def test_validate_number(self):
        assert self.patterns.validate_classification("42") is True
        assert self.patterns.validate_classification("1") is True
        assert self.patterns.validate_classification("100") is True

    def test_validate_invalid(self):
        assert self.patterns.validate_classification("Hello") is False
        assert self.patterns.validate_classification("") is False

    def test_classify_fizz(self):
        assert self.patterns.classify("Fizz") == "Fizz"

    def test_classify_buzz(self):
        assert self.patterns.classify("Buzz") == "Buzz"

    def test_classify_fizzbuzz(self):
        assert self.patterns.classify("FizzBuzz") == "FizzBuzz"

    def test_classify_number(self):
        assert self.patterns.classify("42") == "Number"

    def test_classify_unknown(self):
        assert self.patterns.classify("Hello") == "Unknown"

    def test_get_matcher(self):
        matcher = self.patterns.get_matcher("fizz")
        assert matcher is not None
        assert matcher.is_match("Fizz")

    def test_get_matcher_nonexistent(self):
        assert self.patterns.get_matcher("nonexistent") is None

    def test_get_stats(self):
        stats = self.patterns.get_stats()
        assert len(stats) == 7
        for name, stat in stats.items():
            assert stat.nfa_state_count > 0


# ============================================================
# Benchmark Tests
# ============================================================


class TestRegexBenchmark:
    """Tests for the pathological pattern benchmark."""

    def test_benchmark_runs(self):
        benchmark = RegexBenchmark()
        results = benchmark.run(sizes=[3, 5])
        assert len(results) == 2

    def test_benchmark_results_agree(self):
        benchmark = RegexBenchmark()
        results = benchmark.run(sizes=[3, 5, 8])
        for result in results:
            assert result.results_agree is True

    def test_benchmark_fizzregex_matches(self):
        benchmark = RegexBenchmark()
        results = benchmark.run(sizes=[5])
        assert results[0].fizzregex_matched is True

    def test_benchmark_result_fields(self):
        benchmark = RegexBenchmark()
        results = benchmark.run(sizes=[5])
        r = results[0]
        assert r.input_length == 5
        assert r.fizzregex_time_us >= 0
        assert r.python_re_time_us >= 0
        assert r.speedup_ratio > 0

    def test_benchmark_results_property(self):
        benchmark = RegexBenchmark()
        assert len(benchmark.results) == 0
        benchmark.run(sizes=[3])
        assert len(benchmark.results) == 1


# ============================================================
# Dashboard Tests
# ============================================================


class TestRegexDashboard:
    """Tests for the ASCII regex dashboard."""

    def test_render_with_stats(self):
        stats = {
            "test_pattern": CompilationStats(
                pattern="abc",
                nfa_state_count=6,
                dfa_state_count=4,
                minimized_state_count=3,
                states_eliminated=1,
                total_time_us=50.0,
            ),
        }
        output = RegexDashboard.render(stats)
        assert "FIZZREGEX ENGINE DASHBOARD" in output
        assert "COMPILATION PIPELINE" in output
        assert "MATCHING GUARANTEE" in output

    def test_render_with_benchmark_results(self):
        stats = {
            "test": CompilationStats(
                pattern="a",
                nfa_state_count=2,
                dfa_state_count=2,
                minimized_state_count=2,
                states_eliminated=0,
                total_time_us=10.0,
            ),
        }
        bench = [
            BenchmarkResult(
                pattern="(a?)^5(a)^5",
                input_length=5,
                fizzregex_time_us=10.0,
                python_re_time_us=100.0,
                speedup_ratio=10.0,
                fizzregex_matched=True,
                python_re_matched=True,
                results_agree=True,
            ),
        ]
        output = RegexDashboard.render(stats, benchmark_results=bench)
        assert "BENCHMARK" in output

    def test_render_width(self):
        stats = {}
        output = RegexDashboard.render(stats, width=80)
        lines = output.split("\n")
        # Border lines should be 80 chars
        assert len(lines[0]) == 80


# ============================================================
# Middleware Tests
# ============================================================


class TestRegexMiddleware:
    """Tests for the RegexMiddleware IMiddleware implementation."""

    def test_middleware_name(self):
        mw = RegexMiddleware()
        assert mw.get_name() == "RegexMiddleware"

    def test_middleware_priority(self):
        mw = RegexMiddleware()
        assert isinstance(mw.get_priority(), int)

    def test_middleware_initial_counts(self):
        mw = RegexMiddleware()
        assert mw.match_count == 0
        assert mw.fail_count == 0
        assert mw.total_match_time_us == 0.0

    def test_middleware_patterns_accessible(self):
        mw = RegexMiddleware()
        assert isinstance(mw.patterns, FizzBuzzPatterns)
        assert mw.patterns.pattern_count == 7

    def test_middleware_enable_dashboard_flag(self):
        mw = RegexMiddleware(enable_dashboard=True)
        assert mw.enable_dashboard is True


# ============================================================
# Exception Tests
# ============================================================


class TestRegexExceptions:
    """Tests for regex engine exception hierarchy."""

    def test_regex_engine_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = RegexEngineError("test")
        assert isinstance(err, FizzBuzzError)

    def test_pattern_syntax_error(self):
        err = RegexPatternSyntaxError("abc(", 3, "Missing paren")
        assert err.pattern == "abc("
        assert err.position == 3
        assert "EFP-RX01" in str(err)

    def test_compilation_error(self):
        err = RegexCompilationError("something broke")
        assert "EFP-RX02" in str(err)

    def test_syntax_error_inherits_engine_error(self):
        err = RegexPatternSyntaxError("x", 0, "bad")
        assert isinstance(err, RegexEngineError)


# ============================================================
# Utility Function Tests
# ============================================================


class TestCharMatches:
    """Tests for the _char_matches utility."""

    def test_single_range_match(self):
        assert _char_matches("c", [("a", "z")], False) is True

    def test_single_range_no_match(self):
        assert _char_matches("5", [("a", "z")], False) is False

    def test_negated_match(self):
        assert _char_matches("5", [("a", "z")], True) is True

    def test_negated_no_match(self):
        assert _char_matches("c", [("a", "z")], True) is False

    def test_multiple_ranges(self):
        ranges = [("a", "z"), ("0", "9")]
        assert _char_matches("m", ranges, False) is True
        assert _char_matches("5", ranges, False) is True
        assert _char_matches("!", ranges, False) is False


# ============================================================
# O(n) Guarantee Tests
# ============================================================


class TestOnMatchingGuarantee:
    """Tests verifying the O(n) matching time guarantee.

    These tests compile pathological patterns that cause exponential
    blowup in backtracking engines and verify that FizzRegex handles
    them in bounded time, confirming the DFA-based O(n) guarantee.
    """

    def test_pathological_pattern_completes_in_bounded_time(self):
        """The (a?)^n(a)^n pattern should match a^n in bounded time."""
        compiler = RegexCompiler()
        n = 20
        pattern = "a?" * n + "a" * n
        text = "a" * n

        matcher, stats = compiler.compile(pattern)
        t0 = time.perf_counter()
        result = matcher.full_match(text)
        elapsed = time.perf_counter() - t0

        assert result.matched is True
        # Should complete in well under 1 second (DFA is O(n))
        assert elapsed < 1.0

    def test_nested_quantifiers_bounded(self):
        """Nested quantifiers don't cause exponential blowup."""
        compiler = RegexCompiler()
        # (a*)*b matched against "aaa" (no match, but should be fast)
        pattern = "(a*)*b"
        text = "a" * 20

        matcher, _ = compiler.compile(pattern)
        t0 = time.perf_counter()
        result = matcher.full_match(text)
        elapsed = time.perf_counter() - t0

        assert result.matched is False
        assert elapsed < 1.0

    def test_alternation_explosion_bounded(self):
        """Many alternations don't cause combinatorial explosion."""
        compiler = RegexCompiler()
        pattern = "|".join(f"pattern{i}" for i in range(50))
        text = "pattern25"

        matcher, _ = compiler.compile(pattern)
        t0 = time.perf_counter()
        result = matcher.full_match(text)
        elapsed = time.perf_counter() - t0

        assert result.matched is True
        assert elapsed < 1.0

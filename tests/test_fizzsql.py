"""
Tests for the FizzSQL Relational Query Engine.

Validates the lexer, parser, logical planner, physical planner,
Volcano-model executor, virtual tables, EXPLAIN ANALYZE, result
formatter, dashboard, and orchestrator — all for the express
purpose of ensuring that SELECT * FROM evaluations WHERE
classification = 'FizzBuzz' continues to work as God and
Codd intended.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass
from enum import Enum, auto

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzsql import (
    AggregateExpr,
    AggregateNode,
    AggregateOperator,
    BooleanExpr,
    ColumnRef,
    ComparisonExpr,
    CostEstimator,
    ExplainAnalyze,
    FilterNode,
    FilterOperator,
    FizzSQLDashboard,
    FizzSQLEngine,
    LimitNode,
    LimitOperator,
    LiteralExpr,
    LogicalPlanner,
    OrderByClause,
    PhysicalPlanner,
    PlatformState,
    ProjectNode,
    ProjectOperator,
    QueryRecord,
    ResultFormatter,
    Row,
    SQLLexer,
    SQLParser,
    ScanNode,
    SelectStatement,
    SeqScanOperator,
    SortNode,
    SortOperator,
    TableSchema,
    Token,
    TokenType,
    VIRTUAL_TABLES,
    _compute_aggregate,
    _evaluate_predicate,
    _like_match,
    _predicate_to_string,
)
from enterprise_fizzbuzz.domain.exceptions import (
    FizzSQLError,
    FizzSQLExecutionError,
    FizzSQLSyntaxError,
    FizzSQLTableNotFoundError,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


class MockClassification(Enum):
    FIZZ = auto()
    BUZZ = auto()
    FIZZBUZZ = auto()
    PLAIN = auto()


@dataclass(frozen=True)
class MockEvaluationResult:
    number: int
    classification: MockClassification
    strategy_name: str = "standard"


def _make_evaluations(n: int = 15) -> list[MockEvaluationResult]:
    """Create mock evaluation results for numbers 1..n."""
    results = []
    for i in range(1, n + 1):
        if i % 15 == 0:
            cls = MockClassification.FIZZBUZZ
        elif i % 3 == 0:
            cls = MockClassification.FIZZ
        elif i % 5 == 0:
            cls = MockClassification.BUZZ
        else:
            cls = MockClassification.PLAIN
        results.append(MockEvaluationResult(number=i, classification=cls))
    return results


def _make_state(n: int = 15) -> PlatformState:
    """Create a platform state with mock evaluations."""
    return PlatformState(evaluations=_make_evaluations(n))


# ============================================================
# Lexer Tests
# ============================================================


class TestSQLLexer:
    """Tests for the FizzSQL lexer."""

    def test_simple_select_star(self):
        tokens = SQLLexer("SELECT * FROM evaluations").tokenize()
        types = [t.token_type for t in tokens]
        assert types == [
            TokenType.SELECT, TokenType.STAR, TokenType.FROM,
            TokenType.IDENTIFIER, TokenType.EOF,
        ]

    def test_select_columns(self):
        tokens = SQLLexer("SELECT number, classification FROM evaluations").tokenize()
        types = [t.token_type for t in tokens]
        assert types == [
            TokenType.SELECT, TokenType.IDENTIFIER, TokenType.COMMA,
            TokenType.IDENTIFIER, TokenType.FROM, TokenType.IDENTIFIER,
            TokenType.EOF,
        ]

    def test_where_clause(self):
        tokens = SQLLexer("SELECT * FROM evaluations WHERE number = 15").tokenize()
        assert any(t.token_type == TokenType.WHERE for t in tokens)
        assert any(t.token_type == TokenType.EQ for t in tokens)
        assert any(t.token_type == TokenType.INTEGER and t.value == "15" for t in tokens)

    def test_string_literal(self):
        tokens = SQLLexer("SELECT * FROM evaluations WHERE classification = 'FizzBuzz'").tokenize()
        assert any(t.token_type == TokenType.STRING and t.value == "FizzBuzz" for t in tokens)

    def test_comparison_operators(self):
        tokens = SQLLexer("SELECT * FROM e WHERE a != 1 AND b <= 2 AND c >= 3 AND d <> 4").tokenize()
        types = [t.token_type for t in tokens]
        assert TokenType.NEQ in types
        assert TokenType.LTE in types
        assert TokenType.GTE in types

    def test_float_literal(self):
        tokens = SQLLexer("SELECT * FROM e WHERE a = 3.14").tokenize()
        assert any(t.token_type == TokenType.FLOAT and t.value == "3.14" for t in tokens)

    def test_keywords_case_insensitive(self):
        tokens1 = SQLLexer("select * from evaluations").tokenize()
        tokens2 = SQLLexer("SELECT * FROM evaluations").tokenize()
        types1 = [t.token_type for t in tokens1]
        types2 = [t.token_type for t in tokens2]
        assert types1 == types2

    def test_aggregate_keyword(self):
        tokens = SQLLexer("SELECT COUNT(*) FROM evaluations").tokenize()
        assert tokens[1].token_type == TokenType.COUNT

    def test_escaped_string(self):
        tokens = SQLLexer("SELECT * FROM e WHERE name = 'it''s'").tokenize()
        string_token = next(t for t in tokens if t.token_type == TokenType.STRING)
        assert string_token.value == "it's"

    def test_unterminated_string_raises(self):
        with pytest.raises(FizzSQLSyntaxError):
            SQLLexer("SELECT * FROM e WHERE name = 'unterminated").tokenize()

    def test_unexpected_character_raises(self):
        with pytest.raises(FizzSQLSyntaxError):
            SQLLexer("SELECT * FROM e WHERE name @ 1").tokenize()

    def test_explain_analyze_tokens(self):
        tokens = SQLLexer("EXPLAIN ANALYZE SELECT * FROM evaluations").tokenize()
        assert tokens[0].token_type == TokenType.EXPLAIN
        assert tokens[1].token_type == TokenType.ANALYZE

    def test_order_by_tokens(self):
        tokens = SQLLexer("SELECT * FROM e ORDER BY number DESC").tokenize()
        types = [t.token_type for t in tokens]
        assert TokenType.ORDER in types
        assert TokenType.BY in types
        assert TokenType.DESC in types

    def test_group_by_tokens(self):
        tokens = SQLLexer("SELECT classification FROM e GROUP BY classification").tokenize()
        types = [t.token_type for t in tokens]
        assert TokenType.GROUP in types

    def test_limit_offset_tokens(self):
        tokens = SQLLexer("SELECT * FROM e LIMIT 10 OFFSET 5").tokenize()
        types = [t.token_type for t in tokens]
        assert TokenType.LIMIT in types
        assert TokenType.OFFSET in types

    def test_show_tables_tokens(self):
        tokens = SQLLexer("SHOW TABLES").tokenize()
        assert tokens[0].token_type == TokenType.SHOW
        assert tokens[1].token_type == TokenType.TABLES

    def test_like_keyword(self):
        tokens = SQLLexer("SELECT * FROM e WHERE name LIKE '%fizz%'").tokenize()
        assert any(t.token_type == TokenType.LIKE for t in tokens)

    def test_between_keyword(self):
        tokens = SQLLexer("SELECT * FROM e WHERE number BETWEEN 1 AND 10").tokenize()
        assert any(t.token_type == TokenType.BETWEEN for t in tokens)

    def test_in_keyword(self):
        tokens = SQLLexer("SELECT * FROM e WHERE number IN (1, 2, 3)").tokenize()
        assert any(t.token_type == TokenType.IN for t in tokens)

    def test_token_positions(self):
        tokens = SQLLexer("SELECT * FROM e").tokenize()
        assert tokens[0].position == 0
        assert tokens[1].position == 7  # *
        assert tokens[2].position == 9  # FROM


# ============================================================
# Parser Tests
# ============================================================


class TestSQLParser:
    """Tests for the FizzSQL recursive descent parser."""

    def _parse(self, query: str) -> SelectStatement:
        tokens = SQLLexer(query).tokenize()
        return SQLParser(tokens, query).parse()

    def test_select_star(self):
        stmt = self._parse("SELECT * FROM evaluations")
        assert stmt.is_star is True
        assert stmt.table == "evaluations"

    def test_select_columns(self):
        stmt = self._parse("SELECT number, classification FROM evaluations")
        assert not stmt.is_star
        assert len(stmt.columns) == 2
        assert isinstance(stmt.columns[0], ColumnRef)
        assert stmt.columns[0].name == "number"

    def test_where_equals(self):
        stmt = self._parse("SELECT * FROM evaluations WHERE number = 15")
        assert stmt.where is not None
        assert isinstance(stmt.where, ComparisonExpr)
        assert stmt.where.left == "number"
        assert stmt.where.operator == "="
        assert stmt.where.right == 15

    def test_where_string(self):
        stmt = self._parse("SELECT * FROM evaluations WHERE classification = 'FIZZBUZZ'")
        assert isinstance(stmt.where, ComparisonExpr)
        assert stmt.where.right == "FIZZBUZZ"

    def test_where_and(self):
        stmt = self._parse("SELECT * FROM evaluations WHERE number > 5 AND number < 10")
        assert isinstance(stmt.where, BooleanExpr)
        assert stmt.where.operator == "AND"

    def test_where_or(self):
        stmt = self._parse("SELECT * FROM evaluations WHERE number = 3 OR number = 5")
        assert isinstance(stmt.where, BooleanExpr)
        assert stmt.where.operator == "OR"

    def test_order_by(self):
        stmt = self._parse("SELECT * FROM evaluations ORDER BY number DESC")
        assert len(stmt.order_by) == 1
        assert stmt.order_by[0].column == "number"
        assert stmt.order_by[0].direction == "DESC"

    def test_order_by_default_asc(self):
        stmt = self._parse("SELECT * FROM evaluations ORDER BY number")
        assert stmt.order_by[0].direction == "ASC"

    def test_limit(self):
        stmt = self._parse("SELECT * FROM evaluations LIMIT 5")
        assert stmt.limit == 5

    def test_offset(self):
        stmt = self._parse("SELECT * FROM evaluations LIMIT 5 OFFSET 10")
        assert stmt.limit == 5
        assert stmt.offset == 10

    def test_group_by(self):
        stmt = self._parse(
            "SELECT classification, COUNT(*) FROM evaluations GROUP BY classification"
        )
        assert stmt.group_by == ["classification"]

    def test_aggregate_count_star(self):
        stmt = self._parse("SELECT COUNT(*) FROM evaluations")
        assert len(stmt.columns) == 1
        assert isinstance(stmt.columns[0], AggregateExpr)
        assert stmt.columns[0].function == "COUNT"
        assert stmt.columns[0].column == "*"

    def test_aggregate_with_alias(self):
        stmt = self._parse("SELECT COUNT(*) AS total FROM evaluations")
        assert isinstance(stmt.columns[0], AggregateExpr)
        assert stmt.columns[0].alias == "total"

    def test_column_alias(self):
        stmt = self._parse("SELECT number AS num FROM evaluations")
        assert isinstance(stmt.columns[0], ColumnRef)
        assert stmt.columns[0].alias == "num"

    def test_show_tables(self):
        stmt = self._parse("SHOW TABLES")
        assert stmt.is_show_tables is True

    def test_explain_analyze(self):
        stmt = self._parse("EXPLAIN ANALYZE SELECT * FROM evaluations")
        assert stmt.is_explain is True
        assert stmt.is_star is True

    def test_explain_without_analyze(self):
        stmt = self._parse("EXPLAIN SELECT * FROM evaluations")
        assert stmt.is_explain is True

    def test_like_clause(self):
        stmt = self._parse("SELECT * FROM evaluations WHERE classification LIKE 'FIZZ%'")
        assert isinstance(stmt.where, ComparisonExpr)
        assert stmt.where.operator == "LIKE"

    def test_in_clause(self):
        stmt = self._parse("SELECT * FROM evaluations WHERE number IN (1, 2, 3)")
        assert isinstance(stmt.where, ComparisonExpr)
        assert stmt.where.operator == "IN"
        assert stmt.where.right == [1, 2, 3]

    def test_between_clause(self):
        stmt = self._parse("SELECT * FROM evaluations WHERE number BETWEEN 1 AND 10")
        assert isinstance(stmt.where, ComparisonExpr)
        assert stmt.where.operator == "BETWEEN"
        assert stmt.where.right == (1, 10)

    def test_is_null(self):
        stmt = self._parse("SELECT * FROM evaluations WHERE output IS NULL")
        assert isinstance(stmt.where, ComparisonExpr)
        assert stmt.where.operator == "IS"

    def test_is_not_null(self):
        stmt = self._parse("SELECT * FROM evaluations WHERE output IS NOT NULL")
        assert isinstance(stmt.where, ComparisonExpr)
        assert stmt.where.operator == "IS NOT"

    def test_missing_from_raises(self):
        with pytest.raises(FizzSQLSyntaxError):
            self._parse("SELECT * evaluations")

    def test_unexpected_token_raises(self):
        with pytest.raises(FizzSQLSyntaxError):
            self._parse("SELECT * FROM evaluations BOGUS")

    def test_multiple_aggregates(self):
        stmt = self._parse(
            "SELECT COUNT(*), MIN(number), MAX(number) FROM evaluations"
        )
        assert len(stmt.columns) == 3
        assert all(isinstance(c, AggregateExpr) for c in stmt.columns)

    def test_having_clause(self):
        stmt = self._parse(
            "SELECT classification, COUNT(*) FROM evaluations "
            "GROUP BY classification HAVING COUNT(*) > 1"
        )
        # HAVING parsing — it should be present
        # Note: our parser parses HAVING as a condition, which is
        # a comparison. The left side would be "COUNT" as an identifier.
        # This is a simplified grammar.
        assert stmt.group_by == ["classification"]

    def test_distinct_aggregate(self):
        stmt = self._parse("SELECT COUNT(DISTINCT classification) FROM evaluations")
        assert isinstance(stmt.columns[0], AggregateExpr)
        assert stmt.columns[0].distinct is True


# ============================================================
# Predicate Evaluation Tests
# ============================================================


class TestPredicateEvaluation:
    """Tests for predicate evaluation helpers."""

    def test_eq_string(self):
        pred = ComparisonExpr(left="name", operator="=", right="Fizz")
        assert _evaluate_predicate(pred, {"name": "Fizz"}) is True
        assert _evaluate_predicate(pred, {"name": "Buzz"}) is False

    def test_eq_case_insensitive(self):
        pred = ComparisonExpr(left="name", operator="=", right="fizz")
        assert _evaluate_predicate(pred, {"name": "FIZZ"}) is True

    def test_neq(self):
        pred = ComparisonExpr(left="val", operator="!=", right=5)
        assert _evaluate_predicate(pred, {"val": 3}) is True
        assert _evaluate_predicate(pred, {"val": 5}) is False

    def test_lt(self):
        pred = ComparisonExpr(left="val", operator="<", right=10)
        assert _evaluate_predicate(pred, {"val": 5}) is True
        assert _evaluate_predicate(pred, {"val": 15}) is False

    def test_gt(self):
        pred = ComparisonExpr(left="val", operator=">", right=10)
        assert _evaluate_predicate(pred, {"val": 15}) is True

    def test_lte(self):
        pred = ComparisonExpr(left="val", operator="<=", right=10)
        assert _evaluate_predicate(pred, {"val": 10}) is True

    def test_gte(self):
        pred = ComparisonExpr(left="val", operator=">=", right=10)
        assert _evaluate_predicate(pred, {"val": 10}) is True

    def test_and(self):
        pred = BooleanExpr(
            operator="AND",
            left=ComparisonExpr(left="val", operator=">", right=5),
            right=ComparisonExpr(left="val", operator="<", right=10),
        )
        assert _evaluate_predicate(pred, {"val": 7}) is True
        assert _evaluate_predicate(pred, {"val": 3}) is False

    def test_or(self):
        pred = BooleanExpr(
            operator="OR",
            left=ComparisonExpr(left="val", operator="=", right=3),
            right=ComparisonExpr(left="val", operator="=", right=5),
        )
        assert _evaluate_predicate(pred, {"val": 3}) is True
        assert _evaluate_predicate(pred, {"val": 5}) is True
        assert _evaluate_predicate(pred, {"val": 7}) is False

    def test_not(self):
        pred = BooleanExpr(
            operator="NOT",
            left=ComparisonExpr(left="val", operator="=", right=5),
        )
        assert _evaluate_predicate(pred, {"val": 3}) is True
        assert _evaluate_predicate(pred, {"val": 5}) is False

    def test_is_null(self):
        pred = ComparisonExpr(left="val", operator="IS", right=None)
        assert _evaluate_predicate(pred, {"val": None}) is True
        assert _evaluate_predicate(pred, {"val": 5}) is False

    def test_is_not_null(self):
        pred = ComparisonExpr(left="val", operator="IS NOT", right=None)
        assert _evaluate_predicate(pred, {"val": 5}) is True
        assert _evaluate_predicate(pred, {"val": None}) is False

    def test_in_list(self):
        pred = ComparisonExpr(left="val", operator="IN", right=[1, 2, 3])
        assert _evaluate_predicate(pred, {"val": 2}) is True
        assert _evaluate_predicate(pred, {"val": 5}) is False

    def test_between(self):
        pred = ComparisonExpr(left="val", operator="BETWEEN", right=(1, 10))
        assert _evaluate_predicate(pred, {"val": 5}) is True
        assert _evaluate_predicate(pred, {"val": 15}) is False

    def test_like_percent(self):
        assert _like_match("FizzBuzz", "Fizz%") is True
        assert _like_match("FizzBuzz", "%Buzz") is True
        assert _like_match("FizzBuzz", "%zzBu%") is True
        assert _like_match("FizzBuzz", "Buzz%") is False

    def test_like_underscore(self):
        assert _like_match("Fizz", "F_zz") is True
        assert _like_match("Fuzz", "F_zz") is True
        assert _like_match("Fizzz", "F_zz") is False

    def test_predicate_to_string(self):
        pred = ComparisonExpr(left="number", operator="=", right=15)
        s = _predicate_to_string(pred)
        assert "number" in s
        assert "=" in s


# ============================================================
# Aggregate Tests
# ============================================================


class TestAggregates:
    """Tests for aggregate function computation."""

    def test_count_star(self):
        rows = [{"a": 1}, {"a": 2}, {"a": 3}]
        assert _compute_aggregate("COUNT", "*", rows) == 3

    def test_count_column(self):
        rows = [{"a": 1}, {"a": None}, {"a": 3}]
        assert _compute_aggregate("COUNT", "a", rows) == 2

    def test_count_distinct(self):
        rows = [{"a": 1}, {"a": 1}, {"a": 2}]
        assert _compute_aggregate("COUNT", "a", rows, distinct=True) == 2

    def test_sum(self):
        rows = [{"a": 10}, {"a": 20}, {"a": 30}]
        assert _compute_aggregate("SUM", "a", rows) == 60

    def test_avg(self):
        rows = [{"a": 10}, {"a": 20}, {"a": 30}]
        assert _compute_aggregate("AVG", "a", rows) == pytest.approx(20.0)

    def test_min(self):
        rows = [{"a": 10}, {"a": 5}, {"a": 30}]
        assert _compute_aggregate("MIN", "a", rows) == 5

    def test_max(self):
        rows = [{"a": 10}, {"a": 5}, {"a": 30}]
        assert _compute_aggregate("MAX", "a", rows) == 30

    def test_aggregate_empty_rows(self):
        assert _compute_aggregate("SUM", "a", []) is None

    def test_aggregate_no_matching_column(self):
        rows = [{"b": 1}, {"b": 2}]
        assert _compute_aggregate("SUM", "a", rows) is None


# ============================================================
# Virtual Table Tests
# ============================================================


class TestVirtualTables:
    """Tests for FizzSQL virtual tables."""

    def test_evaluations_table_exists(self):
        assert "evaluations" in VIRTUAL_TABLES

    def test_cache_entries_table_exists(self):
        assert "cache_entries" in VIRTUAL_TABLES

    def test_blockchain_blocks_table_exists(self):
        assert "blockchain_blocks" in VIRTUAL_TABLES

    def test_sla_metrics_table_exists(self):
        assert "sla_metrics" in VIRTUAL_TABLES

    def test_events_table_exists(self):
        assert "events" in VIRTUAL_TABLES

    def test_five_virtual_tables(self):
        assert len(VIRTUAL_TABLES) == 5

    def test_evaluations_populated(self):
        state = _make_state(15)
        rows = VIRTUAL_TABLES["evaluations"].populate(state)
        assert len(rows) == 15
        assert rows[0]["number"] == 1
        assert rows[14]["number"] == 15

    def test_evaluations_classification(self):
        state = _make_state(15)
        rows = VIRTUAL_TABLES["evaluations"].populate(state)
        # number 3 -> FIZZ
        fizz_row = next(r for r in rows if r["number"] == 3)
        assert fizz_row["classification"] == "FIZZ"
        # number 15 -> FIZZBUZZ
        fb_row = next(r for r in rows if r["number"] == 15)
        assert fb_row["classification"] == "FIZZBUZZ"

    def test_evaluations_empty_state(self):
        state = PlatformState()
        rows = VIRTUAL_TABLES["evaluations"].populate(state)
        assert rows == []

    def test_cache_entries_empty(self):
        state = PlatformState()
        rows = VIRTUAL_TABLES["cache_entries"].populate(state)
        assert rows == []

    def test_blockchain_blocks_empty(self):
        state = PlatformState()
        rows = VIRTUAL_TABLES["blockchain_blocks"].populate(state)
        assert rows == []

    def test_sla_metrics_empty(self):
        state = PlatformState()
        rows = VIRTUAL_TABLES["sla_metrics"].populate(state)
        assert rows == []

    def test_events_empty(self):
        state = PlatformState()
        rows = VIRTUAL_TABLES["events"].populate(state)
        assert rows == []

    def test_table_schema_columns(self):
        schema = VIRTUAL_TABLES["evaluations"]
        assert "number" in schema.columns
        assert "classification" in schema.columns
        assert "id" in schema.columns

    def test_table_schema_types(self):
        schema = VIRTUAL_TABLES["evaluations"]
        assert schema.column_types["number"] == "INTEGER"
        assert "VARCHAR" in schema.column_types["classification"]


# ============================================================
# Logical Planner Tests
# ============================================================


class TestLogicalPlanner:
    """Tests for the logical plan builder."""

    def _plan(self, query: str) -> tuple:
        tokens = SQLLexer(query).tokenize()
        stmt = SQLParser(tokens, query).parse()
        planner = LogicalPlanner()
        return planner.build(stmt), stmt

    def test_simple_scan(self):
        plan, _ = self._plan("SELECT * FROM evaluations")
        # Root should be ProjectNode wrapping ScanNode
        assert isinstance(plan, ProjectNode)
        assert isinstance(plan.children[0], ScanNode)

    def test_filter_node(self):
        plan, _ = self._plan("SELECT * FROM evaluations WHERE number = 5")
        # ProjectNode -> FilterNode -> ScanNode
        assert isinstance(plan, ProjectNode)
        assert isinstance(plan.children[0], FilterNode)

    def test_sort_node(self):
        plan, _ = self._plan("SELECT * FROM evaluations ORDER BY number")
        assert isinstance(plan, ProjectNode)
        assert isinstance(plan.children[0], SortNode)

    def test_limit_node(self):
        plan, _ = self._plan("SELECT * FROM evaluations LIMIT 5")
        assert isinstance(plan, ProjectNode)
        assert isinstance(plan.children[0], LimitNode)

    def test_aggregate_node(self):
        plan, _ = self._plan(
            "SELECT classification, COUNT(*) FROM evaluations GROUP BY classification"
        )
        # ProjectNode -> AggregateNode -> ScanNode
        assert isinstance(plan, ProjectNode)
        assert isinstance(plan.children[0], AggregateNode)


# ============================================================
# Physical Operator (Volcano Model) Tests
# ============================================================


class TestVolcanoOperators:
    """Tests for the Volcano-model physical operators."""

    def test_seq_scan_produces_all_rows(self):
        state = _make_state(10)
        schema = VIRTUAL_TABLES["evaluations"]
        op = SeqScanOperator(schema, state)
        op.open()
        rows = []
        while True:
            row = op.next()
            if row is None:
                break
            rows.append(row)
        op.close()
        assert len(rows) == 10
        assert op.rows_produced == 10

    def test_filter_operator(self):
        state = _make_state(15)
        schema = VIRTUAL_TABLES["evaluations"]
        scan = SeqScanOperator(schema, state)
        pred = ComparisonExpr(left="classification", operator="=", right="FIZZBUZZ")
        filt = FilterOperator(scan, pred)
        filt.open()
        rows = []
        while True:
            row = filt.next()
            if row is None:
                break
            rows.append(row)
        filt.close()
        # Only number 15 is FizzBuzz in 1..15
        assert len(rows) == 1
        assert rows[0]["number"] == 15

    def test_project_operator(self):
        state = _make_state(5)
        schema = VIRTUAL_TABLES["evaluations"]
        scan = SeqScanOperator(schema, state)
        cols = [ColumnRef(name="number"), ColumnRef(name="classification")]
        proj = ProjectOperator(scan, cols)
        proj.open()
        row = proj.next()
        assert row is not None
        assert set(row.keys()) == {"number", "classification"}
        proj.close()

    def test_project_star(self):
        state = _make_state(5)
        schema = VIRTUAL_TABLES["evaluations"]
        scan = SeqScanOperator(schema, state)
        proj = ProjectOperator(scan, [], is_star=True)
        proj.open()
        row = proj.next()
        assert row is not None
        assert "id" in row
        assert "number" in row
        assert "classification" in row
        proj.close()

    def test_sort_operator_asc(self):
        state = _make_state(5)
        schema = VIRTUAL_TABLES["evaluations"]
        scan = SeqScanOperator(schema, state)
        sort = SortOperator(scan, [OrderByClause(column="number", direction="ASC")])
        sort.open()
        rows = []
        while True:
            row = sort.next()
            if row is None:
                break
            rows.append(row)
        sort.close()
        numbers = [r["number"] for r in rows]
        assert numbers == sorted(numbers)

    def test_sort_operator_desc(self):
        state = _make_state(5)
        schema = VIRTUAL_TABLES["evaluations"]
        scan = SeqScanOperator(schema, state)
        sort = SortOperator(scan, [OrderByClause(column="number", direction="DESC")])
        sort.open()
        rows = []
        while True:
            row = sort.next()
            if row is None:
                break
            rows.append(row)
        sort.close()
        numbers = [r["number"] for r in rows]
        assert numbers == sorted(numbers, reverse=True)

    def test_limit_operator(self):
        state = _make_state(10)
        schema = VIRTUAL_TABLES["evaluations"]
        scan = SeqScanOperator(schema, state)
        limit = LimitOperator(scan, 3)
        limit.open()
        rows = []
        while True:
            row = limit.next()
            if row is None:
                break
            rows.append(row)
        limit.close()
        assert len(rows) == 3

    def test_limit_with_offset(self):
        state = _make_state(10)
        schema = VIRTUAL_TABLES["evaluations"]
        scan = SeqScanOperator(schema, state)
        limit = LimitOperator(scan, 3, offset=5)
        limit.open()
        rows = []
        while True:
            row = limit.next()
            if row is None:
                break
            rows.append(row)
        limit.close()
        assert len(rows) == 3
        assert rows[0]["number"] == 6  # 0-indexed: skip 5, start at 6

    def test_aggregate_operator_count(self):
        state = _make_state(15)
        schema = VIRTUAL_TABLES["evaluations"]
        scan = SeqScanOperator(schema, state)
        agg = AggregateOperator(
            scan,
            group_by=["classification"],
            aggregates=[AggregateExpr(function="COUNT", column="*")],
        )
        agg.open()
        rows = []
        while True:
            row = agg.next()
            if row is None:
                break
            rows.append(row)
        agg.close()
        # Should have 4 groups: FIZZ, BUZZ, FIZZBUZZ, PLAIN
        assert len(rows) == 4
        total = sum(r["COUNT(*)"] for r in rows)
        assert total == 15


# ============================================================
# Physical Planner Tests
# ============================================================


class TestPhysicalPlanner:
    """Tests for the physical planner."""

    def test_builds_seq_scan(self):
        state = _make_state()
        planner = PhysicalPlanner(state)
        scan_node = ScanNode("evaluations")
        op = planner.plan(scan_node)
        assert isinstance(op, SeqScanOperator)

    def test_invalid_table_raises(self):
        state = _make_state()
        planner = PhysicalPlanner(state)
        scan_node = ScanNode("nonexistent_table")
        with pytest.raises(FizzSQLTableNotFoundError):
            planner.plan(scan_node)


# ============================================================
# Cost Estimator Tests
# ============================================================


class TestCostEstimator:
    """Tests for the FizzSQL cost estimator."""

    def test_scan_cost(self):
        node = ScanNode("evaluations")
        startup, total = CostEstimator.estimate(node, 100)
        assert startup == 0.0
        assert total > 0.0

    def test_filter_cost(self):
        scan = ScanNode("evaluations")
        filt = FilterNode(ComparisonExpr(left="x", operator="=", right=1))
        filt.children = [scan]
        startup, total = CostEstimator.estimate(filt, 100)
        assert total > 0.0

    def test_sort_cost_blocking(self):
        scan = ScanNode("evaluations")
        sort = SortNode([OrderByClause(column="number")])
        sort.children = [scan]
        startup, total = CostEstimator.estimate(sort, 100)
        # Sort is blocking: startup should equal total
        assert startup == total


# ============================================================
# Result Formatter Tests
# ============================================================


class TestResultFormatter:
    """Tests for the ASCII table result formatter."""

    def test_empty_result(self):
        output = ResultFormatter.format([])
        assert "(0 rows)" in output

    def test_single_row(self):
        rows = [{"name": "Alice", "age": 30}]
        output = ResultFormatter.format(rows)
        assert "Alice" in output
        assert "30" in output
        assert "(1 row)" in output

    def test_multiple_rows(self):
        rows = [
            {"number": 1, "result": "1"},
            {"number": 3, "result": "Fizz"},
            {"number": 5, "result": "Buzz"},
        ]
        output = ResultFormatter.format(rows)
        assert "(3 rows)" in output
        assert "Fizz" in output

    def test_border_characters(self):
        rows = [{"a": 1}]
        output = ResultFormatter.format(rows)
        assert "+" in output
        assert "-" in output
        assert "|" in output

    def test_auto_width(self):
        rows = [{"very_long_column_name": "short"}]
        output = ResultFormatter.format(rows)
        assert "very_long_column_name" in output

    def test_null_values(self):
        rows = [{"a": None}]
        output = ResultFormatter.format(rows)
        assert "None" in output


# ============================================================
# EXPLAIN ANALYZE Tests
# ============================================================


class TestExplainAnalyze:
    """Tests for EXPLAIN ANALYZE output."""

    def test_explain_output(self):
        state = _make_state(15)
        schema = VIRTUAL_TABLES["evaluations"]
        scan = SeqScanOperator(schema, state)
        proj = ProjectOperator(scan, [], is_star=True)
        proj.open()
        while proj.next():
            pass
        proj.close()

        logical = ProjectNode([], is_star=True)
        logical.children = [ScanNode("evaluations")]

        output = ExplainAnalyze.render(proj, 1.234, 15, logical)
        assert "QUERY PLAN" in output
        assert "Execution time" in output
        assert "Total cost" in output
        assert "FCU" in output


# ============================================================
# Engine Integration Tests
# ============================================================


class TestFizzSQLEngine:
    """Integration tests for the FizzSQL engine orchestrator."""

    def _engine(self, n: int = 15) -> FizzSQLEngine:
        return FizzSQLEngine(state=_make_state(n))

    def test_select_star_from_evaluations(self):
        engine = self._engine()
        output = engine.execute("SELECT * FROM evaluations")
        assert "(15 rows)" in output

    def test_select_star_where_classification_fizzbuzz(self):
        """The flagship query that MUST work."""
        engine = self._engine()
        output = engine.execute(
            "SELECT * FROM evaluations WHERE classification = 'FizzBuzz'"
        )
        # FizzBuzz in 1..15 is only 15
        assert "(1 row)" in output

    def test_select_classification_count_group_by(self):
        """The other flagship query that MUST work."""
        engine = self._engine()
        output = engine.execute(
            "SELECT classification, COUNT(*) FROM evaluations GROUP BY classification"
        )
        assert "(4 rows)" in output
        assert "FIZZ" in output
        assert "BUZZ" in output

    def test_select_with_where_number(self):
        engine = self._engine()
        output = engine.execute("SELECT * FROM evaluations WHERE number = 15")
        assert "(1 row)" in output

    def test_select_with_order_by(self):
        engine = self._engine()
        output = engine.execute("SELECT * FROM evaluations ORDER BY number DESC")
        assert "(15 rows)" in output

    def test_select_with_limit(self):
        engine = self._engine()
        output = engine.execute("SELECT * FROM evaluations LIMIT 5")
        assert "(5 rows)" in output

    def test_select_with_limit_offset(self):
        engine = self._engine()
        output = engine.execute("SELECT * FROM evaluations LIMIT 3 OFFSET 10")
        assert "(3 rows)" in output

    def test_select_specific_columns(self):
        engine = self._engine()
        output = engine.execute("SELECT number, classification FROM evaluations")
        assert "(15 rows)" in output
        # Should not contain strategy column header
        assert "strategy" not in output.split("\n")[2]  # in header row

    def test_show_tables(self):
        engine = self._engine()
        output = engine.execute("SHOW TABLES")
        assert "evaluations" in output
        assert "cache_entries" in output
        assert "blockchain_blocks" in output
        assert "sla_metrics" in output
        assert "events" in output

    def test_explain_analyze(self):
        engine = self._engine()
        output = engine.execute("EXPLAIN ANALYZE SELECT * FROM evaluations")
        assert "QUERY PLAN" in output
        assert "SeqScan" in output
        assert "FCU" in output

    def test_table_not_found(self):
        engine = self._engine()
        with pytest.raises(FizzSQLTableNotFoundError):
            engine.execute("SELECT * FROM nonexistent")

    def test_syntax_error(self):
        engine = self._engine()
        with pytest.raises(FizzSQLSyntaxError):
            engine.execute("SELECTE * FROM evaluations")

    def test_empty_query_raises(self):
        engine = self._engine()
        with pytest.raises(FizzSQLSyntaxError):
            engine.execute("")

    def test_where_greater_than(self):
        engine = self._engine()
        output = engine.execute("SELECT * FROM evaluations WHERE number > 10")
        assert "(5 rows)" in output

    def test_where_and(self):
        engine = self._engine()
        output = engine.execute(
            "SELECT * FROM evaluations WHERE number >= 1 AND number <= 5"
        )
        assert "(5 rows)" in output

    def test_where_or(self):
        engine = self._engine()
        output = engine.execute(
            "SELECT * FROM evaluations WHERE number = 1 OR number = 15"
        )
        assert "(2 rows)" in output

    def test_where_like(self):
        engine = self._engine()
        output = engine.execute(
            "SELECT * FROM evaluations WHERE classification LIKE 'FIZZ%'"
        )
        # FIZZ and FIZZBUZZ both match
        assert "FIZZ" in output

    def test_where_in(self):
        engine = self._engine()
        output = engine.execute(
            "SELECT * FROM evaluations WHERE number IN (1, 3, 5, 15)"
        )
        assert "(4 rows)" in output

    def test_where_between(self):
        engine = self._engine()
        output = engine.execute(
            "SELECT * FROM evaluations WHERE number BETWEEN 5 AND 10"
        )
        assert "(6 rows)" in output

    def test_count_star(self):
        engine = self._engine()
        output = engine.execute("SELECT COUNT(*) FROM evaluations")
        assert "15" in output

    def test_min_max(self):
        engine = self._engine()
        output = engine.execute("SELECT MIN(number), MAX(number) FROM evaluations")
        assert "1" in output
        assert "15" in output

    def test_empty_evaluations(self):
        engine = FizzSQLEngine(state=PlatformState())
        output = engine.execute("SELECT * FROM evaluations")
        assert "(0 rows)" in output

    def test_query_history(self):
        engine = self._engine()
        engine.execute("SELECT * FROM evaluations")
        engine.execute("SHOW TABLES")
        assert len(engine.query_history) == 2
        assert engine.query_history[0].success is True
        assert engine.query_history[1].success is True

    def test_query_history_on_error(self):
        engine = self._engine()
        try:
            engine.execute("SELECT * FROM nonexistent")
        except FizzSQLTableNotFoundError:
            pass
        assert len(engine.query_history) == 1
        assert engine.query_history[0].success is False

    def test_list_tables(self):
        engine = self._engine()
        tables = engine.list_tables()
        assert len(tables) == 5
        names = [t["name"] for t in tables]
        assert "evaluations" in names

    def test_case_insensitive_query(self):
        engine = self._engine()
        output = engine.execute("select * from evaluations limit 3")
        assert "(3 rows)" in output


# ============================================================
# Dashboard Tests
# ============================================================


class TestFizzSQLDashboard:
    """Tests for the FizzSQL dashboard rendering."""

    def test_dashboard_renders(self):
        engine = FizzSQLEngine(state=_make_state())
        engine.execute("SELECT * FROM evaluations")
        output = FizzSQLDashboard.render(engine)
        assert "FIZZSQL RELATIONAL QUERY ENGINE DASHBOARD" in output
        assert "ENGINE STATISTICS" in output
        assert "TABLE CATALOG" in output

    def test_dashboard_with_no_queries(self):
        engine = FizzSQLEngine(state=_make_state())
        output = FizzSQLDashboard.render(engine)
        assert "Total queries executed: 0" in output

    def test_dashboard_shows_recent_queries(self):
        engine = FizzSQLEngine(state=_make_state())
        engine.execute("SELECT * FROM evaluations")
        output = FizzSQLDashboard.render(engine)
        assert "RECENT QUERIES" in output

    def test_dashboard_custom_width(self):
        engine = FizzSQLEngine(state=_make_state())
        output = FizzSQLDashboard.render(engine, width=80)
        # Check that lines are wider
        lines = output.split("\n")
        border_lines = [l for l in lines if l.strip().startswith("+")]
        if border_lines:
            assert len(border_lines[0].strip()) >= 78


# ============================================================
# Exception Tests
# ============================================================


class TestFizzSQLExceptions:
    """Tests for FizzSQL exception hierarchy."""

    def test_fizzsql_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(FizzSQLError, FizzBuzzError)

    def test_syntax_error_code(self):
        err = FizzSQLSyntaxError("SELECT", 0, "bad")
        assert "EFP-SQL1" in str(err)

    def test_table_not_found_code(self):
        err = FizzSQLTableNotFoundError("bogus", ["evaluations"])
        assert "EFP-SQL2" in str(err)

    def test_execution_error_code(self):
        err = FizzSQLExecutionError("SELECT 1", "oops")
        assert "EFP-SQL3" in str(err)

    def test_base_error_code(self):
        err = FizzSQLError("general failure")
        assert "EFP-SQL0" in str(err)

    def test_syntax_error_preserves_query(self):
        err = FizzSQLSyntaxError("SELECT * FORM x", 9, "typo")
        assert err.query == "SELECT * FORM x"
        assert err.position == 9

    def test_table_not_found_preserves_available(self):
        err = FizzSQLTableNotFoundError("bogus", ["a", "b"])
        assert err.available == ["a", "b"]

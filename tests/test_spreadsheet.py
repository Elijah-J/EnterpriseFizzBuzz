"""
Enterprise FizzBuzz Platform - FizzSheet Spreadsheet Engine Test Suite

Comprehensive test coverage for the FizzSheet spreadsheet engine, validating
cell reference parsing, formula lexing and parsing, operator precedence,
dependency graph construction, Kahn's topological sort, circular reference
detection, built-in function evaluation, FizzBuzz-specific functions,
spreadsheet grid operations, ASCII rendering, dashboard generation,
and middleware integration.

The tests are organized by component:
1. Cell reference parsing and validation
2. Cell value types and coercion
3. Formula lexer tokenization
4. Formula parser — literals, operators, precedence, functions, ranges
5. Formula evaluator — arithmetic, comparison, functions
6. Dependency graph — edges, topological sort, downstream collection
7. Circular reference detection
8. Spreadsheet grid operations — set, get, clear, recalculate
9. Built-in functions — SUM, AVERAGE, COUNT, MAX, MIN, IF, etc.
10. FizzBuzz-specific functions — FIZZBUZZ, FIZZBUZZ_COST, FIZZBUZZ_TAX
11. Row and column insert/delete operations
12. Spreadsheet renderer — ASCII table output
13. Spreadsheet dashboard — statistics and metrics
14. Middleware integration — pipeline processing
15. Standalone formula evaluation
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.infrastructure.spreadsheet import (
    Cell,
    CellRef,
    CellValue,
    CellValueType,
    CircularReferenceDetector,
    DependencyGraph,
    FormulaEvaluator,
    FormulaLexer,
    FormulaParser,
    NumberNode,
    StringNode,
    BooleanNode,
    CellRefNode,
    RangeNode,
    FunctionCallNode,
    BinaryOpNode,
    UnaryOpNode,
    FormulaNodeType,
    Spreadsheet,
    SpreadsheetDashboard,
    SpreadsheetMiddleware,
    SpreadsheetRenderer,
    TokenType,
    evaluate_formula,
    COLUMN_LETTERS,
    MAX_COLUMNS,
    MAX_ROWS,
)
from enterprise_fizzbuzz.domain.exceptions import (
    SpreadsheetCellReferenceError,
    SpreadsheetCircularReferenceError,
    SpreadsheetError,
    SpreadsheetFormulaParseError,
    SpreadsheetFunctionError,
    SpreadsheetRangeError,
)


# ============================================================
# Cell Reference Tests
# ============================================================


class TestCellRef:
    """Tests for A1-style cell reference parsing and validation."""

    def test_create_valid_ref(self):
        ref = CellRef("A", 1)
        assert ref.col == "A"
        assert ref.row == 1

    def test_create_ref_max_row(self):
        ref = CellRef("Z", 999)
        assert ref.col == "Z"
        assert ref.row == 999

    def test_from_string_simple(self):
        ref = CellRef.from_string("A1")
        assert ref.col == "A"
        assert ref.row == 1

    def test_from_string_case_insensitive(self):
        ref = CellRef.from_string("b5")
        assert ref.col == "B"
        assert ref.row == 5

    def test_from_string_with_whitespace(self):
        ref = CellRef.from_string("  C10  ")
        assert ref.col == "C"
        assert ref.row == 10

    def test_col_index(self):
        assert CellRef("A", 1).col_index == 0
        assert CellRef("B", 1).col_index == 1
        assert CellRef("Z", 1).col_index == 25

    def test_str_representation(self):
        assert str(CellRef("A", 1)) == "A1"
        assert str(CellRef("Z", 999)) == "Z999"

    def test_invalid_column_raises(self):
        with pytest.raises(SpreadsheetCellReferenceError):
            CellRef("1", 1)

    def test_invalid_row_zero_raises(self):
        with pytest.raises(SpreadsheetCellReferenceError):
            CellRef("A", 0)

    def test_invalid_row_exceeds_max_raises(self):
        with pytest.raises(SpreadsheetCellReferenceError):
            CellRef("A", 1000)

    def test_from_string_invalid_raises(self):
        with pytest.raises(SpreadsheetCellReferenceError):
            CellRef.from_string("AA1")

    def test_from_string_no_digits_raises(self):
        with pytest.raises(SpreadsheetCellReferenceError):
            CellRef.from_string("A")

    def test_frozen_ref(self):
        ref = CellRef("A", 1)
        with pytest.raises(AttributeError):
            ref.col = "B"

    def test_equality(self):
        assert CellRef("A", 1) == CellRef("A", 1)
        assert CellRef("A", 1) != CellRef("B", 1)

    def test_hashable(self):
        s = {CellRef("A", 1), CellRef("A", 1), CellRef("B", 2)}
        assert len(s) == 2


# ============================================================
# Cell Value Tests
# ============================================================


class TestCellValue:
    """Tests for typed cell values and type coercion."""

    def test_number_value(self):
        v = CellValue.number(42.0)
        assert v.is_number
        assert v.raw == 42.0

    def test_string_value(self):
        v = CellValue.string("hello")
        assert v.is_string
        assert v.raw == "hello"

    def test_boolean_value(self):
        v = CellValue.boolean(True)
        assert v.is_boolean
        assert v.raw is True

    def test_error_value(self):
        v = CellValue.error("#DIV/0!")
        assert v.is_error
        assert v.raw == "#DIV/0!"

    def test_empty_value(self):
        v = CellValue.empty()
        assert v.is_empty
        assert v.raw is None

    def test_number_to_string_integer(self):
        v = CellValue.number(42.0)
        assert v.to_string() == "42"

    def test_number_to_string_decimal(self):
        v = CellValue.number(3.14159)
        assert v.to_string() == "3.14159"

    def test_boolean_to_string(self):
        assert CellValue.boolean(True).to_string() == "TRUE"
        assert CellValue.boolean(False).to_string() == "FALSE"

    def test_empty_to_string(self):
        assert CellValue.empty().to_string() == ""

    def test_number_to_number(self):
        assert CellValue.number(5.0).to_number() == 5.0

    def test_boolean_to_number(self):
        assert CellValue.boolean(True).to_number() == 1.0
        assert CellValue.boolean(False).to_number() == 0.0

    def test_empty_to_number(self):
        assert CellValue.empty().to_number() == 0.0

    def test_string_to_number_valid(self):
        assert CellValue.string("42").to_number() == 42.0

    def test_string_to_number_invalid_raises(self):
        with pytest.raises(SpreadsheetFunctionError):
            CellValue.string("hello").to_number()


# ============================================================
# Formula Lexer Tests
# ============================================================


class TestFormulaLexer:
    """Tests for formula tokenization."""

    def test_number_token(self):
        tokens = FormulaLexer("42").tokenize()
        assert tokens[0].token_type == TokenType.NUMBER
        assert tokens[0].value == 42.0

    def test_decimal_number(self):
        tokens = FormulaLexer("3.14").tokenize()
        assert tokens[0].token_type == TokenType.NUMBER
        assert tokens[0].value == 3.14

    def test_string_token(self):
        tokens = FormulaLexer('"hello"').tokenize()
        assert tokens[0].token_type == TokenType.STRING
        assert tokens[0].value == "hello"

    def test_cell_ref_token(self):
        tokens = FormulaLexer("A1").tokenize()
        assert tokens[0].token_type == TokenType.CELL_REF
        assert tokens[0].value == "A1"

    def test_function_name_token(self):
        tokens = FormulaLexer("SUM").tokenize()
        assert tokens[0].token_type == TokenType.IDENT
        assert tokens[0].value == "SUM"

    def test_operators(self):
        tokens = FormulaLexer("+-*/^").tokenize()
        types = [t.token_type for t in tokens[:-1]]
        assert types == [
            TokenType.PLUS, TokenType.MINUS, TokenType.STAR,
            TokenType.SLASH, TokenType.CARET,
        ]

    def test_comparison_operators(self):
        tokens = FormulaLexer("< > <= >= <> =").tokenize()
        types = [t.token_type for t in tokens[:-1]]
        assert types == [
            TokenType.LT, TokenType.GT, TokenType.LTE,
            TokenType.GTE, TokenType.NEQ, TokenType.EQ,
        ]

    def test_parentheses_and_comma(self):
        tokens = FormulaLexer("(,)").tokenize()
        types = [t.token_type for t in tokens[:-1]]
        assert types == [TokenType.LPAREN, TokenType.COMMA, TokenType.RPAREN]

    def test_colon_token(self):
        tokens = FormulaLexer(":").tokenize()
        assert tokens[0].token_type == TokenType.COLON

    def test_unterminated_string_raises(self):
        with pytest.raises(SpreadsheetFormulaParseError):
            FormulaLexer('"hello').tokenize()

    def test_unexpected_character_raises(self):
        with pytest.raises(SpreadsheetFormulaParseError):
            FormulaLexer("@").tokenize()

    def test_whitespace_ignored(self):
        tokens = FormulaLexer("  1  +  2  ").tokenize()
        assert len(tokens) == 4  # NUMBER, PLUS, NUMBER, EOF


# ============================================================
# Formula Parser Tests
# ============================================================


class TestFormulaParser:
    """Tests for recursive-descent formula parsing."""

    def test_parse_number(self):
        node = FormulaParser("=42").parse()
        assert isinstance(node, NumberNode)
        assert node.value == 42.0

    def test_parse_string(self):
        node = FormulaParser('="hello"').parse()
        assert isinstance(node, StringNode)
        assert node.value == "hello"

    def test_parse_boolean_true(self):
        node = FormulaParser("=TRUE").parse()
        assert isinstance(node, BooleanNode)
        assert node.value is True

    def test_parse_boolean_false(self):
        node = FormulaParser("=FALSE").parse()
        assert isinstance(node, BooleanNode)
        assert node.value is False

    def test_parse_cell_ref(self):
        node = FormulaParser("=A1").parse()
        assert isinstance(node, CellRefNode)
        assert node.ref == CellRef("A", 1)

    def test_parse_cell_range(self):
        node = FormulaParser("=A1:B5").parse()
        assert isinstance(node, RangeNode)
        assert node.start == CellRef("A", 1)
        assert node.end == CellRef("B", 5)

    def test_parse_function_call(self):
        node = FormulaParser("=SUM(A1:A10)").parse()
        assert isinstance(node, FunctionCallNode)
        assert node.name == "SUM"
        assert len(node.args) == 1

    def test_parse_function_multiple_args(self):
        node = FormulaParser("=IF(A1, B1, C1)").parse()
        assert isinstance(node, FunctionCallNode)
        assert node.name == "IF"
        assert len(node.args) == 3

    def test_parse_addition(self):
        node = FormulaParser("=1+2").parse()
        assert isinstance(node, BinaryOpNode)
        assert node.op == "+"

    def test_parse_subtraction(self):
        node = FormulaParser("=5-3").parse()
        assert isinstance(node, BinaryOpNode)
        assert node.op == "-"

    def test_parse_multiplication(self):
        node = FormulaParser("=2*3").parse()
        assert isinstance(node, BinaryOpNode)
        assert node.op == "*"

    def test_parse_division(self):
        node = FormulaParser("=10/2").parse()
        assert isinstance(node, BinaryOpNode)
        assert node.op == "/"

    def test_parse_power(self):
        node = FormulaParser("=2^3").parse()
        assert isinstance(node, BinaryOpNode)
        assert node.op == "^"

    def test_parse_unary_minus(self):
        node = FormulaParser("=-5").parse()
        assert isinstance(node, UnaryOpNode)
        assert node.op == "-"

    def test_precedence_mul_over_add(self):
        # 1 + 2 * 3 should parse as 1 + (2 * 3)
        node = FormulaParser("=1+2*3").parse()
        assert isinstance(node, BinaryOpNode)
        assert node.op == "+"
        assert isinstance(node.right, BinaryOpNode)
        assert node.right.op == "*"

    def test_precedence_power_over_mul(self):
        # 2 * 3 ^ 2 should parse as 2 * (3 ^ 2)
        node = FormulaParser("=2*3^2").parse()
        assert isinstance(node, BinaryOpNode)
        assert node.op == "*"
        assert isinstance(node.right, BinaryOpNode)
        assert node.right.op == "^"

    def test_precedence_comparison_lowest(self):
        # A1 + 1 > 5 should parse as (A1 + 1) > 5
        node = FormulaParser("=A1+1>5").parse()
        assert isinstance(node, BinaryOpNode)
        assert node.op == ">"
        assert isinstance(node.left, BinaryOpNode)
        assert node.left.op == "+"

    def test_parenthesized_expression(self):
        # (1 + 2) * 3
        node = FormulaParser("=(1+2)*3").parse()
        assert isinstance(node, BinaryOpNode)
        assert node.op == "*"
        assert isinstance(node.left, BinaryOpNode)
        assert node.left.op == "+"

    def test_power_right_associative(self):
        # 2 ^ 3 ^ 2 should parse as 2 ^ (3 ^ 2)
        node = FormulaParser("=2^3^2").parse()
        assert isinstance(node, BinaryOpNode)
        assert node.op == "^"
        assert isinstance(node.right, BinaryOpNode)
        assert node.right.op == "^"

    def test_parse_without_equals(self):
        # Parser should handle formulas without leading '='
        node = FormulaParser("42").parse()
        assert isinstance(node, NumberNode)

    def test_unexpected_token_raises(self):
        with pytest.raises(SpreadsheetFormulaParseError):
            FormulaParser("=1 2").parse()

    def test_unknown_identifier_raises(self):
        with pytest.raises(SpreadsheetFormulaParseError):
            FormulaParser("=FOOBAR").parse()

    def test_nested_function_calls(self):
        node = FormulaParser("=SUM(A1, MAX(B1, C1))").parse()
        assert isinstance(node, FunctionCallNode)
        assert node.name == "SUM"
        assert isinstance(node.args[1], FunctionCallNode)
        assert node.args[1].name == "MAX"


# ============================================================
# Dependency Graph Tests
# ============================================================


class TestDependencyGraph:
    """Tests for the directed dependency graph and Kahn's topological sort."""

    def test_add_dependency(self):
        g = DependencyGraph()
        g.add_dependency("B1", "A1")
        assert "B1" in g.get_dependents("A1")
        assert "A1" in g.get_dependencies("B1")

    def test_remove_cell(self):
        g = DependencyGraph()
        g.add_dependency("B1", "A1")
        g.remove_cell("B1")
        assert "B1" not in g.get_dependents("A1")

    def test_topological_order_simple(self):
        g = DependencyGraph()
        g.add_dependency("B1", "A1")
        g.add_dependency("C1", "B1")
        order = g.topological_order()
        assert order.index("A1") < order.index("B1")
        assert order.index("B1") < order.index("C1")

    def test_topological_order_diamond(self):
        g = DependencyGraph()
        g.add_dependency("B1", "A1")
        g.add_dependency("C1", "A1")
        g.add_dependency("D1", "B1")
        g.add_dependency("D1", "C1")
        order = g.topological_order()
        assert order.index("A1") < order.index("B1")
        assert order.index("A1") < order.index("C1")
        assert order.index("B1") < order.index("D1")
        assert order.index("C1") < order.index("D1")

    def test_topological_order_cycle_raises(self):
        g = DependencyGraph()
        g.add_dependency("B1", "A1")
        g.add_dependency("A1", "B1")
        with pytest.raises(SpreadsheetCircularReferenceError):
            g.topological_order()

    def test_topological_order_with_dirty_cells(self):
        g = DependencyGraph()
        g.add_dependency("B1", "A1")
        g.add_dependency("C1", "A1")
        g.add_dependency("D1", "C1")
        order = g.topological_order(dirty_cells={"C1"})
        assert "C1" in order
        assert "D1" in order
        # A1 and B1 should not be included since they're not downstream of C1
        # (C1 depends on A1, but we only go downstream from C1)

    def test_all_edges(self):
        g = DependencyGraph()
        g.add_dependency("B1", "A1")
        g.add_dependency("C1", "A1")
        edges = g.all_edges
        assert ("A1", "B1") in edges
        assert ("A1", "C1") in edges

    def test_cell_count(self):
        g = DependencyGraph()
        g.add_dependency("B1", "A1")
        assert g.cell_count == 2

    def test_empty_graph(self):
        g = DependencyGraph()
        assert g.topological_order() == []
        assert g.cell_count == 0


# ============================================================
# Circular Reference Detector Tests
# ============================================================


class TestCircularReferenceDetector:
    """Tests for DFS-based cycle detection."""

    def test_no_cycle(self):
        g = DependencyGraph()
        g.add_dependency("B1", "A1")
        g.add_dependency("C1", "B1")
        detector = CircularReferenceDetector(g)
        assert not detector.has_cycle()

    def test_direct_cycle(self):
        g = DependencyGraph()
        g.add_dependency("B1", "A1")
        g.add_dependency("A1", "B1")
        detector = CircularReferenceDetector(g)
        assert detector.has_cycle()

    def test_indirect_cycle(self):
        g = DependencyGraph()
        g.add_dependency("B1", "A1")
        g.add_dependency("C1", "B1")
        g.add_dependency("A1", "C1")
        detector = CircularReferenceDetector(g)
        assert detector.has_cycle()

    def test_find_cycle_returns_cells(self):
        g = DependencyGraph()
        g.add_dependency("B1", "A1")
        g.add_dependency("A1", "B1")
        detector = CircularReferenceDetector(g)
        cycle = detector.find_cycle()
        assert len(cycle) > 0

    def test_empty_graph_no_cycle(self):
        g = DependencyGraph()
        detector = CircularReferenceDetector(g)
        assert not detector.has_cycle()


# ============================================================
# Spreadsheet Grid Tests
# ============================================================


class TestSpreadsheet:
    """Tests for the spreadsheet grid operations."""

    def test_set_and_get_number(self):
        s = Spreadsheet()
        s.set_cell("A1", "42")
        val = s.get_cell("A1")
        assert val.is_number
        assert val.raw == 42.0

    def test_set_and_get_string(self):
        s = Spreadsheet()
        s.set_cell("A1", "hello")
        val = s.get_cell("A1")
        assert val.is_string
        assert val.raw == "hello"

    def test_set_and_get_boolean(self):
        s = Spreadsheet()
        s.set_cell("A1", "TRUE")
        val = s.get_cell("A1")
        assert val.is_boolean
        assert val.raw is True

    def test_get_empty_cell(self):
        s = Spreadsheet()
        val = s.get_cell("A1")
        assert val.is_empty

    def test_formula_addition(self):
        s = Spreadsheet()
        s.set_cell("A1", "10")
        s.set_cell("A2", "20")
        s.set_cell("A3", "=A1+A2")
        val = s.get_cell("A3")
        assert val.is_number
        assert val.raw == 30.0

    def test_formula_with_cell_ref(self):
        s = Spreadsheet()
        s.set_cell("A1", "5")
        s.set_cell("B1", "=A1*2")
        assert s.get_cell("B1").raw == 10.0

    def test_cascading_recalculation(self):
        s = Spreadsheet()
        s.set_cell("A1", "1")
        s.set_cell("B1", "=A1+1")
        s.set_cell("C1", "=B1+1")
        assert s.get_cell("C1").raw == 3.0
        # Update A1 triggers cascade
        s.set_cell("A1", "10")
        assert s.get_cell("B1").raw == 11.0
        assert s.get_cell("C1").raw == 12.0

    def test_circular_reference_detected(self):
        s = Spreadsheet()
        s.set_cell("A1", "=B1")
        s.set_cell("B1", "=A1")
        val = s.get_cell("B1")
        assert val.is_error
        assert "CIRCULAR" in val.raw

    def test_clear_cell(self):
        s = Spreadsheet()
        s.set_cell("A1", "42")
        s.clear_cell("A1")
        assert s.get_cell("A1").is_empty

    def test_get_raw_formula(self):
        s = Spreadsheet()
        s.set_cell("A1", "=1+2")
        assert s.get_raw("A1") == "=1+2"

    def test_get_raw_empty(self):
        s = Spreadsheet()
        assert s.get_raw("A1") == ""

    def test_formula_parse_error(self):
        s = Spreadsheet()
        s.set_cell("A1", "=@@@")
        val = s.get_cell("A1")
        assert val.is_error
        assert "PARSE" in val.raw

    def test_used_range_single_cell(self):
        s = Spreadsheet()
        s.set_cell("B3", "hello")
        tl, br = s.get_used_range()
        assert tl == CellRef("B", 3)
        assert br == CellRef("B", 3)

    def test_used_range_multiple_cells(self):
        s = Spreadsheet()
        s.set_cell("A1", "1")
        s.set_cell("C5", "2")
        tl, br = s.get_used_range()
        assert tl == CellRef("A", 1)
        assert br == CellRef("C", 5)

    def test_recalculate_all(self):
        s = Spreadsheet()
        s.set_cell("A1", "5")
        s.set_cell("B1", "=A1*2")
        s.recalculate_all()
        assert s.get_cell("B1").raw == 10.0

    def test_cellref_object_argument(self):
        s = Spreadsheet()
        ref = CellRef("A", 1)
        s.set_cell(ref, "100")
        assert s.get_cell(ref).raw == 100.0


# ============================================================
# Built-in Function Tests
# ============================================================


class TestBuiltinFunctions:
    """Tests for the 20 built-in spreadsheet functions."""

    def _eval(self, formula: str, cells: dict[str, str] = None) -> CellValue:
        """Helper to evaluate a formula with optional pre-populated cells."""
        s = Spreadsheet()
        if cells:
            for ref, val in cells.items():
                s.set_cell(ref, val)
        s.set_cell("Z999", formula)
        return s.get_cell("Z999")

    def test_sum_range(self):
        result = self._eval("=SUM(A1:A3)", {"A1": "1", "A2": "2", "A3": "3"})
        assert result.raw == 6.0

    def test_sum_individual(self):
        result = self._eval("=SUM(A1, B1)", {"A1": "10", "B1": "20"})
        assert result.raw == 30.0

    def test_average(self):
        result = self._eval("=AVERAGE(A1:A3)", {"A1": "10", "A2": "20", "A3": "30"})
        assert result.raw == 20.0

    def test_average_empty_range(self):
        result = self._eval("=AVERAGE(A1:A3)")
        assert result.is_error

    def test_count(self):
        result = self._eval("=COUNT(A1:A3)", {"A1": "1", "A2": "hello", "A3": "3"})
        assert result.raw == 2.0  # "hello" is not counted

    def test_max(self):
        result = self._eval("=MAX(A1:A3)", {"A1": "5", "A2": "15", "A3": "10"})
        assert result.raw == 15.0

    def test_min(self):
        result = self._eval("=MIN(A1:A3)", {"A1": "5", "A2": "15", "A3": "10"})
        assert result.raw == 5.0

    def test_if_true(self):
        result = self._eval("=IF(TRUE, 1, 2)")
        assert result.raw == 1.0

    def test_if_false(self):
        result = self._eval("=IF(FALSE, 1, 2)")
        assert result.raw == 2.0

    def test_if_numeric_condition(self):
        result = self._eval("=IF(1, 10, 20)")
        assert result.raw == 10.0

    def test_if_zero_is_false(self):
        result = self._eval("=IF(0, 10, 20)")
        assert result.raw == 20.0

    def test_and_true(self):
        result = self._eval("=AND(TRUE, TRUE)")
        assert result.is_boolean
        assert result.raw is True

    def test_and_false(self):
        result = self._eval("=AND(TRUE, FALSE)")
        assert result.raw is False

    def test_or_true(self):
        result = self._eval("=OR(FALSE, TRUE)")
        assert result.raw is True

    def test_or_false(self):
        result = self._eval("=OR(FALSE, FALSE)")
        assert result.raw is False

    def test_not_true(self):
        result = self._eval("=NOT(TRUE)")
        assert result.raw is False

    def test_not_false(self):
        result = self._eval("=NOT(FALSE)")
        assert result.raw is True

    def test_concatenate(self):
        result = self._eval('=CONCATENATE("Fizz", "Buzz")')
        assert result.raw == "FizzBuzz"

    def test_len(self):
        result = self._eval('=LEN("hello")')
        assert result.raw == 5.0

    def test_abs_positive(self):
        result = self._eval("=ABS(5)")
        assert result.raw == 5.0

    def test_abs_negative(self):
        result = self._eval("=ABS(-5)")
        assert result.raw == 5.0

    def test_mod(self):
        result = self._eval("=MOD(10, 3)")
        assert result.raw == 1.0

    def test_mod_division_by_zero(self):
        result = self._eval("=MOD(10, 0)")
        assert result.is_error

    def test_power(self):
        result = self._eval("=POWER(2, 10)")
        assert result.raw == 1024.0

    def test_round(self):
        result = self._eval("=ROUND(3.14159, 2)")
        assert result.raw == 3.14

    def test_upper(self):
        result = self._eval('=UPPER("hello")')
        assert result.raw == "HELLO"

    def test_lower(self):
        result = self._eval('=LOWER("HELLO")')
        assert result.raw == "hello"

    def test_unknown_function(self):
        result = self._eval("=NOSUCHFUNC(1)")
        assert result.is_error
        assert "NAME" in result.raw


# ============================================================
# FizzBuzz-Specific Function Tests
# ============================================================


class TestFizzBuzzFunctions:
    """Tests for FIZZBUZZ, FIZZBUZZ_COST, and FIZZBUZZ_TAX functions."""

    def _eval(self, formula: str) -> CellValue:
        return evaluate_formula(formula)

    def test_fizzbuzz_fizzbuzz(self):
        result = self._eval("=FIZZBUZZ(15)")
        assert result.is_string
        assert result.raw == "FizzBuzz"

    def test_fizzbuzz_fizz(self):
        result = self._eval("=FIZZBUZZ(9)")
        assert result.is_string
        assert result.raw == "Fizz"

    def test_fizzbuzz_buzz(self):
        result = self._eval("=FIZZBUZZ(10)")
        assert result.is_string
        assert result.raw == "Buzz"

    def test_fizzbuzz_plain(self):
        result = self._eval("=FIZZBUZZ(7)")
        assert result.is_number
        assert result.raw == 7.0

    def test_fizzbuzz_zero(self):
        result = self._eval("=FIZZBUZZ(0)")
        assert result.raw == "FizzBuzz"

    def test_fizzbuzz_30(self):
        result = self._eval("=FIZZBUZZ(30)")
        assert result.raw == "FizzBuzz"

    def test_fizzbuzz_cost_fizzbuzz(self):
        result = self._eval("=FIZZBUZZ_COST(15)")
        assert result.raw == 0.15

    def test_fizzbuzz_cost_fizz(self):
        result = self._eval("=FIZZBUZZ_COST(3)")
        assert result.raw == 0.03

    def test_fizzbuzz_cost_buzz(self):
        result = self._eval("=FIZZBUZZ_COST(5)")
        assert result.raw == 0.05

    def test_fizzbuzz_cost_plain(self):
        result = self._eval("=FIZZBUZZ_COST(7)")
        assert result.raw == 0.01

    def test_fizzbuzz_tax_fizzbuzz(self):
        result = self._eval("=FIZZBUZZ_TAX(15)")
        assert result.raw == 0.15

    def test_fizzbuzz_tax_fizz(self):
        result = self._eval("=FIZZBUZZ_TAX(3)")
        assert result.raw == 0.03

    def test_fizzbuzz_tax_buzz(self):
        result = self._eval("=FIZZBUZZ_TAX(5)")
        assert result.raw == 0.05

    def test_fizzbuzz_tax_plain(self):
        result = self._eval("=FIZZBUZZ_TAX(7)")
        assert result.raw == 0.0

    def test_fizzbuzz_wrong_args(self):
        result = self._eval("=FIZZBUZZ(1, 2)")
        assert result.is_error

    def test_fizzbuzz_cost_wrong_args(self):
        result = self._eval("=FIZZBUZZ_COST()")
        assert result.is_error

    def test_fizzbuzz_tax_wrong_args(self):
        result = self._eval("=FIZZBUZZ_TAX(1, 2, 3)")
        assert result.is_error


# ============================================================
# Row/Column Operations Tests
# ============================================================


class TestRowColumnOperations:
    """Tests for insert/delete row and column operations."""

    def test_insert_row(self):
        s = Spreadsheet()
        s.set_cell("A1", "first")
        s.set_cell("A2", "second")
        s.insert_row(2)
        # A1 stays, A2 shifted to A3
        assert s.get_cell("A1").raw == "first"
        assert s.get_cell("A3").raw == "second"

    def test_delete_row(self):
        s = Spreadsheet()
        s.set_cell("A1", "first")
        s.set_cell("A2", "to_delete")
        s.set_cell("A3", "third")
        s.delete_row(2)
        assert s.get_cell("A1").raw == "first"
        assert s.get_cell("A2").raw == "third"

    def test_insert_column(self):
        s = Spreadsheet()
        s.set_cell("A1", "col_a")
        s.set_cell("B1", "col_b")
        s.insert_column("B")
        assert s.get_cell("A1").raw == "col_a"
        assert s.get_cell("C1").raw == "col_b"

    def test_delete_column(self):
        s = Spreadsheet()
        s.set_cell("A1", "col_a")
        s.set_cell("B1", "to_delete")
        s.set_cell("C1", "col_c")
        s.delete_column("B")
        assert s.get_cell("A1").raw == "col_a"
        assert s.get_cell("B1").raw == "col_c"

    def test_insert_row_invalid_raises(self):
        s = Spreadsheet()
        with pytest.raises(SpreadsheetRangeError):
            s.insert_row(0)

    def test_delete_row_invalid_raises(self):
        s = Spreadsheet()
        with pytest.raises(SpreadsheetRangeError):
            s.delete_row(0)

    def test_insert_column_invalid_raises(self):
        s = Spreadsheet()
        with pytest.raises(SpreadsheetRangeError):
            s.insert_column("1")

    def test_delete_column_invalid_raises(self):
        s = Spreadsheet()
        with pytest.raises(SpreadsheetRangeError):
            s.delete_column("1")


# ============================================================
# Renderer Tests
# ============================================================


class TestSpreadsheetRenderer:
    """Tests for ASCII table rendering."""

    def test_empty_sheet(self):
        s = Spreadsheet()
        renderer = SpreadsheetRenderer()
        output = renderer.render(s)
        assert "empty" in output.lower()

    def test_single_cell_renders(self):
        s = Spreadsheet()
        s.set_cell("A1", "42")
        renderer = SpreadsheetRenderer()
        output = renderer.render(s)
        assert "42" in output
        assert "A" in output

    def test_multiple_columns(self):
        s = Spreadsheet()
        s.set_cell("A1", "1")
        s.set_cell("B1", "2")
        s.set_cell("C1", "3")
        renderer = SpreadsheetRenderer()
        output = renderer.render(s)
        assert "A" in output
        assert "B" in output
        assert "C" in output

    def test_number_right_aligned(self):
        s = Spreadsheet()
        s.set_cell("A1", "42")
        renderer = SpreadsheetRenderer()
        output = renderer.render(s)
        # Number should be present in the output
        assert "42" in output

    def test_string_left_aligned(self):
        s = Spreadsheet()
        s.set_cell("A1", "hello")
        renderer = SpreadsheetRenderer()
        output = renderer.render(s)
        assert "hello" in output


# ============================================================
# Dashboard Tests
# ============================================================


class TestSpreadsheetDashboard:
    """Tests for the FizzSheet ASCII dashboard."""

    def test_empty_sheet_dashboard(self):
        s = Spreadsheet()
        output = SpreadsheetDashboard.render(s)
        assert "FIZZSHEET" in output
        assert "Total cells: 0" in output

    def test_dashboard_with_cells(self):
        s = Spreadsheet()
        s.set_cell("A1", "42")
        s.set_cell("A2", "hello")
        s.set_cell("A3", "=A1+1")
        output = SpreadsheetDashboard.render(s)
        assert "Total cells: 3" in output
        assert "Formula cells: 1" in output
        assert "Literal cells: 2" in output

    def test_dashboard_function_usage(self):
        s = Spreadsheet()
        s.set_cell("A1", "5")
        s.set_cell("A2", "=SUM(A1, A1)")
        output = SpreadsheetDashboard.render(s)
        assert "SUM" in output

    def test_dashboard_dependency_graph(self):
        s = Spreadsheet()
        s.set_cell("A1", "5")
        s.set_cell("B1", "=A1*2")
        output = SpreadsheetDashboard.render(s)
        assert "Dependency Graph" in output
        assert "Edges" in output

    def test_dashboard_performance_metrics(self):
        s = Spreadsheet()
        s.set_cell("A1", "=1+2")
        output = SpreadsheetDashboard.render(s)
        assert "Cell evaluations" in output
        assert "Recalculation passes" in output


# ============================================================
# Middleware Tests
# ============================================================


class TestSpreadsheetMiddleware:
    """Tests for the SpreadsheetMiddleware pipeline integration."""

    def test_middleware_name(self):
        mw = SpreadsheetMiddleware()
        assert mw.get_name() == "SpreadsheetMiddleware"

    def test_middleware_priority(self):
        mw = SpreadsheetMiddleware()
        assert mw.get_priority() == 8

    def test_middleware_exposes_spreadsheet(self):
        mw = SpreadsheetMiddleware()
        assert isinstance(mw.spreadsheet, Spreadsheet)

    def test_middleware_custom_spreadsheet(self):
        s = Spreadsheet()
        mw = SpreadsheetMiddleware(spreadsheet=s)
        assert mw.spreadsheet is s


# ============================================================
# Standalone Formula Evaluation Tests
# ============================================================


class TestStandaloneEvaluation:
    """Tests for the evaluate_formula convenience function."""

    def test_simple_arithmetic(self):
        result = evaluate_formula("=1+2+3")
        assert result.raw == 6.0

    def test_string_literal(self):
        result = evaluate_formula('="hello"')
        assert result.raw == "hello"

    def test_fizzbuzz_function(self):
        result = evaluate_formula("=FIZZBUZZ(15)")
        assert result.raw == "FizzBuzz"

    def test_nested_functions(self):
        result = evaluate_formula("=SUM(1, 2, 3)")
        assert result.raw == 6.0

    def test_division_by_zero(self):
        result = evaluate_formula("=1/0")
        assert result.is_error
        assert "DIV" in result.raw

    def test_comparison(self):
        result = evaluate_formula("=5>3")
        assert result.is_boolean
        assert result.raw is True

    def test_complex_expression(self):
        result = evaluate_formula("=IF(FIZZBUZZ(15)=\"FizzBuzz\", 100, 0)")
        # FIZZBUZZ(15) returns "FizzBuzz", comparison with = should be TRUE
        # But the comparison is string vs string
        assert result.raw == 100.0


# ============================================================
# Edge Case Tests
# ============================================================


class TestEdgeCases:
    """Tests for various edge cases and error conditions."""

    def test_deeply_nested_formulas(self):
        s = Spreadsheet()
        s.set_cell("A1", "1")
        s.set_cell("A2", "=A1+1")
        s.set_cell("A3", "=A2+1")
        s.set_cell("A4", "=A3+1")
        s.set_cell("A5", "=A4+1")
        assert s.get_cell("A5").raw == 5.0

    def test_self_reference_circular(self):
        s = Spreadsheet()
        s.set_cell("A1", "=A1")
        val = s.get_cell("A1")
        assert val.is_error
        assert "CIRCULAR" in val.raw

    def test_overwrite_cell(self):
        s = Spreadsheet()
        s.set_cell("A1", "42")
        s.set_cell("A1", "99")
        assert s.get_cell("A1").raw == 99.0

    def test_overwrite_formula_with_literal(self):
        s = Spreadsheet()
        s.set_cell("A1", "=1+2")
        assert s.get_cell("A1").raw == 3.0
        s.set_cell("A1", "42")
        assert s.get_cell("A1").raw == 42.0

    def test_empty_string_is_empty(self):
        s = Spreadsheet()
        s.set_cell("A1", "")
        assert s.get_cell("A1").is_empty

    def test_unary_minus_in_formula(self):
        result = evaluate_formula("=-5")
        assert result.raw == -5.0

    def test_unary_plus_in_formula(self):
        result = evaluate_formula("=+5")
        assert result.raw == 5.0

    def test_multiple_unary(self):
        result = evaluate_formula("=--5")
        assert result.raw == 5.0

    def test_sum_empty_range(self):
        result = evaluate_formula("=SUM(A1:A5)")
        assert result.raw == 0.0

    def test_max_empty_range(self):
        result = evaluate_formula("=MAX(A1:A5)")
        assert result.raw == 0.0

    def test_range_outside_function_returns_error(self):
        s = Spreadsheet()
        s.set_cell("A1", "=B1:B5")
        val = s.get_cell("A1")
        assert val.is_error

    def test_fizzbuzz_comprehensive_range(self):
        """Verify FIZZBUZZ function against the first 30 numbers."""
        expected = {
            1: 1, 2: 2, 3: "Fizz", 4: 4, 5: "Buzz",
            6: "Fizz", 7: 7, 8: 8, 9: "Fizz", 10: "Buzz",
            11: 11, 12: "Fizz", 13: 13, 14: 14, 15: "FizzBuzz",
            16: 16, 17: 17, 18: "Fizz", 19: 19, 20: "Buzz",
            21: "Fizz", 22: 22, 23: 23, 24: "Fizz", 25: "Buzz",
            26: 26, 27: "Fizz", 28: 28, 29: 29, 30: "FizzBuzz",
        }
        for n, exp in expected.items():
            result = evaluate_formula(f"=FIZZBUZZ({n})")
            if isinstance(exp, str):
                assert result.raw == exp, f"FIZZBUZZ({n}) expected {exp!r}, got {result.raw!r}"
            else:
                assert result.raw == float(exp), f"FIZZBUZZ({n}) expected {exp}, got {result.raw}"

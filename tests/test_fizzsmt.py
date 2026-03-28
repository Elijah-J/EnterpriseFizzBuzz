"""
Enterprise FizzBuzz Platform - FizzSMT Solver Tests

Comprehensive test suite for the FizzSMT subsystem, which provides a
Satisfiability Modulo Theories (SMT) solver for constraint satisfaction
over integer, boolean, real, and bitvector domains.

Covers: SortType enum, Variable and Constraint dataclasses, SolverResult
enum, Solution dataclass, SMTSolver declaration and constraint management,
satisfiability checking with brute-force search, FizzSMTDashboard rendering,
FizzSMTMiddleware pipeline integration, create_fizzsmt_subsystem factory,
and the exception hierarchy.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.domain.exceptions.fizzsmt import (
    FizzSMTError,
    FizzSMTNotFoundError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)
from enterprise_fizzbuzz.infrastructure.fizzsmt import (
    FIZZSMT_VERSION,
    MIDDLEWARE_PRIORITY,
    Constraint,
    FizzSMTDashboard,
    FizzSMTMiddleware,
    SMTSolver,
    Solution,
    SolverResult,
    SortType,
    Variable,
    create_fizzsmt_subsystem,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def solver():
    """A fresh SMTSolver instance."""
    return SMTSolver()


# ---------------------------------------------------------------------------
# Module-level constant tests
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Tests for the FizzSMT module-level exports."""

    def test_version_string(self):
        assert FIZZSMT_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 222


# ---------------------------------------------------------------------------
# SortType enum tests
# ---------------------------------------------------------------------------


class TestSortTypeEnum:
    """Tests for the SortType enumeration of SMT-LIB sort kinds."""

    def test_bool_sort_exists(self):
        assert SortType.BOOL is not None

    def test_int_sort_exists(self):
        assert SortType.INT is not None

    def test_real_sort_exists(self):
        assert SortType.REAL is not None

    def test_bitvec_sort_exists(self):
        assert SortType.BITVEC is not None


# ---------------------------------------------------------------------------
# Variable dataclass tests
# ---------------------------------------------------------------------------


class TestVariableDataclass:
    """Tests for the Variable dataclass structure."""

    def test_variable_fields(self):
        v = Variable(name="x", sort=SortType.INT)
        assert v.name == "x"
        assert v.sort == SortType.INT

    def test_variable_with_bool_sort(self):
        v = Variable(name="flag", sort=SortType.BOOL)
        assert v.sort == SortType.BOOL


# ---------------------------------------------------------------------------
# Constraint dataclass tests
# ---------------------------------------------------------------------------


class TestConstraintDataclass:
    """Tests for the Constraint dataclass structure."""

    def test_constraint_fields(self):
        c = Constraint(
            constraint_id="c-001",
            expression="x > 5",
            variables=["x"],
        )
        assert c.constraint_id == "c-001"
        assert c.expression == "x > 5"
        assert c.variables == ["x"]

    def test_constraint_with_multiple_variables(self):
        c = Constraint(
            constraint_id="c-002",
            expression="x + y == 15",
            variables=["x", "y"],
        )
        assert len(c.variables) == 2


# ---------------------------------------------------------------------------
# SolverResult enum tests
# ---------------------------------------------------------------------------


class TestSolverResultEnum:
    """Tests for the SolverResult enumeration of solver outcomes."""

    def test_sat_result_exists(self):
        assert SolverResult.SAT is not None

    def test_unsat_result_exists(self):
        assert SolverResult.UNSAT is not None

    def test_unknown_result_exists(self):
        assert SolverResult.UNKNOWN is not None


# ---------------------------------------------------------------------------
# Solution dataclass tests
# ---------------------------------------------------------------------------


class TestSolutionDataclass:
    """Tests for the Solution dataclass carrying solver output."""

    def test_solution_sat_fields(self):
        sol = Solution(
            result=SolverResult.SAT,
            model={"x": 10},
            constraints_checked=1,
        )
        assert sol.result == SolverResult.SAT
        assert sol.model["x"] == 10
        assert sol.constraints_checked == 1

    def test_solution_unsat_has_empty_model(self):
        sol = Solution(
            result=SolverResult.UNSAT,
            model={},
            constraints_checked=3,
        )
        assert sol.model == {}


# ---------------------------------------------------------------------------
# SMTSolver: variable declaration tests
# ---------------------------------------------------------------------------


class TestSMTSolverDeclaration:
    """Tests for variable declaration and retrieval on the solver."""

    def test_declare_returns_variable(self, solver):
        v = solver.declare("x", SortType.INT)
        assert isinstance(v, Variable)
        assert v.name == "x"
        assert v.sort == SortType.INT

    def test_get_variable_returns_declared(self, solver):
        solver.declare("alpha", SortType.REAL)
        v = solver.get_variable("alpha")
        assert v.name == "alpha"
        assert v.sort == SortType.REAL

    def test_list_variables_returns_all_declared(self, solver):
        solver.declare("a", SortType.INT)
        solver.declare("b", SortType.BOOL)
        variables = solver.list_variables()
        names = [v.name for v in variables]
        assert "a" in names
        assert "b" in names
        assert len(variables) == 2


# ---------------------------------------------------------------------------
# SMTSolver: constraint management tests
# ---------------------------------------------------------------------------


class TestSMTSolverConstraints:
    """Tests for adding and listing constraints."""

    def test_add_constraint_returns_constraint(self, solver):
        solver.declare("x", SortType.INT)
        c = solver.add_constraint("x > 5", ["x"])
        assert isinstance(c, Constraint)
        assert c.expression == "x > 5"
        assert "x" in c.variables

    def test_list_constraints_returns_all(self, solver):
        solver.declare("x", SortType.INT)
        solver.declare("y", SortType.INT)
        solver.add_constraint("x > 0", ["x"])
        solver.add_constraint("y > 0", ["y"])
        constraints = solver.list_constraints()
        assert len(constraints) == 2


# ---------------------------------------------------------------------------
# SMTSolver: solve tests
# ---------------------------------------------------------------------------


class TestSMTSolverSolve:
    """Tests for the satisfiability search engine."""

    def test_simple_satisfiable_constraint(self, solver):
        solver.declare("x", SortType.INT)
        solver.add_constraint("x > 5", ["x"])
        solution = solver.solve()
        assert solution.result == SolverResult.SAT
        assert solution.model["x"] > 5

    def test_multiple_satisfiable_constraints(self, solver):
        solver.declare("x", SortType.INT)
        solver.add_constraint("x > 0", ["x"])
        solver.add_constraint("x < 10", ["x"])
        solution = solver.solve()
        assert solution.result == SolverResult.SAT
        assert 0 < solution.model["x"] < 10

    def test_fizzbuzz_divisibility_constraint(self, solver):
        solver.declare("x", SortType.INT)
        solver.add_constraint("x % 3 == 0", ["x"])
        solver.add_constraint("x % 5 == 0", ["x"])
        solver.add_constraint("x > 0", ["x"])
        solution = solver.solve()
        assert solution.result == SolverResult.SAT
        assert solution.model["x"] % 15 == 0

    def test_equality_constraint(self, solver):
        solver.declare("x", SortType.INT)
        solver.add_constraint("x + 0 == 7", ["x"])
        solution = solver.solve()
        assert solution.result == SolverResult.SAT
        assert solution.model["x"] == 7

    def test_constraints_checked_is_positive(self, solver):
        solver.declare("x", SortType.INT)
        solver.add_constraint("x > 0", ["x"])
        solution = solver.solve()
        assert solution.constraints_checked > 0

    def test_solve_with_no_constraints_is_sat(self, solver):
        solver.declare("x", SortType.INT)
        solution = solver.solve()
        assert solution.result == SolverResult.SAT


# ---------------------------------------------------------------------------
# SMTSolver: reset tests
# ---------------------------------------------------------------------------


class TestSMTSolverReset:
    """Tests for clearing all solver state."""

    def test_reset_clears_variables(self, solver):
        solver.declare("x", SortType.INT)
        solver.reset()
        assert solver.list_variables() == []

    def test_reset_clears_constraints(self, solver):
        solver.declare("x", SortType.INT)
        solver.add_constraint("x > 0", ["x"])
        solver.reset()
        assert solver.list_constraints() == []


# ---------------------------------------------------------------------------
# FizzSMTDashboard tests
# ---------------------------------------------------------------------------


class TestFizzSMTDashboard:
    """Tests for the FizzSMT monitoring dashboard."""

    def test_render_returns_string(self):
        solver = SMTSolver()
        dashboard = FizzSMTDashboard(solver)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_smt_identifier(self):
        solver = SMTSolver()
        dashboard = FizzSMTDashboard(solver)
        output = dashboard.render().lower()
        assert "smt" in output


# ---------------------------------------------------------------------------
# FizzSMTMiddleware tests
# ---------------------------------------------------------------------------


class TestFizzSMTMiddleware:
    """Tests for the FizzSMT middleware pipeline integration."""

    def test_middleware_name_and_priority(self, solver):
        mw = FizzSMTMiddleware(solver)
        assert mw.get_name() == "fizzsmt"
        assert mw.get_priority() == 222

    def test_middleware_passes_through_context(self, solver):
        mw = FizzSMTMiddleware(solver)
        ctx = ProcessingContext(number=15, session_id="test-smt-session")

        def next_handler(c: ProcessingContext) -> ProcessingContext:
            c.results.append(FizzBuzzResult(number=15, output="FizzBuzz"))
            return c

        result = mw.process(ctx, next_handler)
        assert len(result.results) == 1
        assert result.results[0].output == "FizzBuzz"
        assert result.results[0].number == 15


# ---------------------------------------------------------------------------
# Factory function tests
# ---------------------------------------------------------------------------


class TestCreateFizzSMTSubsystem:
    """Tests for the create_fizzsmt_subsystem factory."""

    def test_returns_solver_dashboard_middleware_tuple(self):
        result = create_fizzsmt_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3
        s, d, m = result
        assert isinstance(s, SMTSolver)
        assert isinstance(d, FizzSMTDashboard)
        assert isinstance(m, FizzSMTMiddleware)

    def test_factory_components_are_wired(self):
        s, d, m = create_fizzsmt_subsystem()
        assert d.render() is not None
        assert m.get_name() == "fizzsmt"


# ---------------------------------------------------------------------------
# Exception hierarchy tests
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """Tests for the FizzSMT exception classes."""

    def test_not_found_is_subclass_of_fizzsmt_error(self):
        assert issubclass(FizzSMTNotFoundError, FizzSMTError)

    def test_fizzsmt_error_message_contains_reason(self):
        err = FizzSMTError("unsatisfiable constraint set")
        assert "unsatisfiable constraint set" in str(err)

    def test_not_found_error_contains_identifier(self):
        err = FizzSMTNotFoundError("variable_z")
        assert "variable_z" in str(err)

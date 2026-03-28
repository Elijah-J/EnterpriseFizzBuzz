"""Enterprise FizzBuzz Platform - FizzSMT: SMT Constraint Solver"""
from __future__ import annotations
import logging, re, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzsmt import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzsmt")
EVENT_SMT = EventType.register("FIZZSMT_SOLVED")
FIZZSMT_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 222


class SortType(Enum):
    BOOL = "bool"
    INT = "int"
    REAL = "real"
    BITVEC = "bitvec"


class SolverResult(Enum):
    SAT = "sat"
    UNSAT = "unsat"
    UNKNOWN = "unknown"


@dataclass
class Variable:
    name: str = ""
    sort: SortType = SortType.INT


@dataclass
class Constraint:
    constraint_id: str = ""
    expression: str = ""
    variables: List[str] = field(default_factory=list)


@dataclass
class Solution:
    result: SolverResult = SolverResult.UNKNOWN
    model: Dict[str, Any] = field(default_factory=dict)
    constraints_checked: int = 0


@dataclass
class FizzSMTConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


class SMTSolver:
    """Satisfiability Modulo Theories solver for integer arithmetic constraints.
    Uses brute-force enumeration over a bounded domain for simple constraints."""

    SEARCH_RANGE = range(-100, 101)

    def __init__(self) -> None:
        self._variables: OrderedDict[str, Variable] = OrderedDict()
        self._constraints: List[Constraint] = []

    def declare(self, name: str, sort: SortType = SortType.INT) -> Variable:
        var = Variable(name=name, sort=sort)
        self._variables[name] = var
        return var

    def add_constraint(self, expression: str, variables: List[str]) -> Constraint:
        c = Constraint(
            constraint_id=f"c-{uuid.uuid4().hex[:8]}",
            expression=expression,
            variables=list(variables),
        )
        self._constraints.append(c)
        return c

    def solve(self) -> Solution:
        """Attempt to find a satisfying assignment for all constraints."""
        if not self._constraints:
            return Solution(result=SolverResult.SAT, model={}, constraints_checked=0)

        var_names = list(self._variables.keys())
        if not var_names:
            return Solution(result=SolverResult.UNKNOWN, model={}, constraints_checked=0)

        checked = 0
        # Brute force for small variable counts
        if len(var_names) <= 3:
            return self._brute_force(var_names, checked)
        return Solution(result=SolverResult.UNKNOWN, model={}, constraints_checked=0)

    def _brute_force(self, var_names: List[str], checked: int) -> Solution:
        """Brute-force search over bounded integer domain."""
        from itertools import product
        ranges = [self.SEARCH_RANGE] * len(var_names)
        for values in product(*ranges):
            checked += 1
            assignment = dict(zip(var_names, values))
            if self._check_all(assignment):
                return Solution(
                    result=SolverResult.SAT,
                    model=assignment,
                    constraints_checked=checked,
                )
            if checked > 50000:
                break
        return Solution(result=SolverResult.UNSAT, model={}, constraints_checked=checked)

    def _check_all(self, assignment: Dict[str, int]) -> bool:
        """Check if an assignment satisfies all constraints."""
        for c in self._constraints:
            if not self._evaluate(c.expression, assignment):
                return False
        return True

    def _evaluate(self, expression: str, assignment: Dict[str, int]) -> bool:
        """Evaluate a simple arithmetic expression with the given assignment."""
        expr = expression
        for name, value in sorted(assignment.items(), key=lambda x: -len(x[0])):
            expr = expr.replace(name, str(value))
        try:
            return bool(eval(expr))  # noqa: S307
        except Exception:
            return False

    def get_variable(self, name: str) -> Variable:
        var = self._variables.get(name)
        if var is None:
            raise FizzSMTNotFoundError(name)
        return var

    def list_variables(self) -> List[Variable]:
        return list(self._variables.values())

    def list_constraints(self) -> List[Constraint]:
        return list(self._constraints)

    def reset(self) -> None:
        self._variables.clear()
        self._constraints.clear()


class FizzSMTDashboard:
    def __init__(self, solver: Optional[SMTSolver] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._solver = solver; self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzSMT Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZSMT_VERSION}"]
        if self._solver:
            lines.append(f"  Variables: {len(self._solver.list_variables())}")
            lines.append(f"  Constraints: {len(self._solver.list_constraints())}")
        return "\n".join(lines)


class FizzSMTMiddleware(IMiddleware):
    def __init__(self, solver: Optional[SMTSolver] = None,
                 dashboard: Optional[FizzSMTDashboard] = None) -> None:
        self._solver = solver; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzsmt"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzsmt_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[SMTSolver, FizzSMTDashboard, FizzSMTMiddleware]:
    solver = SMTSolver()
    dashboard = FizzSMTDashboard(solver, dashboard_width)
    middleware = FizzSMTMiddleware(solver, dashboard)
    logger.info("FizzSMT initialized")
    return solver, dashboard, middleware

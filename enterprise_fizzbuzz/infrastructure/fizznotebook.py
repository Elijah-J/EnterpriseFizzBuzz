"""
Enterprise FizzBuzz Platform - FizzNotebook: Interactive Computational Notebook

Production-grade computational notebook for the Enterprise FizzBuzz Platform.
Implements cell-based execution with code, markdown, and output cells,
persistent kernel sessions with variable namespace, FizzLang evaluation
integration, rich output rendering (text, tables, charts as ASCII),
magic commands (%fizzbuzz, %time, %who, %reset), checkpoint/undo,
notebook serialization, HTML/Markdown export, cell reordering, and
notebook diffing for version control integration.

FizzNotebook fills the interactive exploration gap -- FizzLang has an LSP,
a debugger, and a REPL, but no notebook interface for literate FizzBuzz
evaluation where prose, code, and results coexist.

Architecture reference: Jupyter Notebook 7, Observable, Google Colab.
"""

from __future__ import annotations

import copy
import json
import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions.fizznotebook import (
    FizzNotebookError, FizzNotebookKernelError, FizzNotebookCellError,
    FizzNotebookExecutionError, FizzNotebookNotFoundError,
    FizzNotebookExistsError, FizzNotebookFormatError, FizzNotebookExportError,
    FizzNotebookWidgetError, FizzNotebookSessionError,
    FizzNotebookCheckpointError, FizzNotebookDiffError,
    FizzNotebookVariableError, FizzNotebookMagicError, FizzNotebookConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, FizzBuzzResult, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizznotebook")

EVENT_NB_CELL_EXECUTED = EventType.register("FIZZNOTEBOOK_CELL_EXECUTED")
EVENT_NB_SAVED = EventType.register("FIZZNOTEBOOK_SAVED")

FIZZNOTEBOOK_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 136


class CellType(Enum):
    CODE = "code"
    MARKDOWN = "markdown"
    RAW = "raw"

class CellStatus(Enum):
    IDLE = auto()
    RUNNING = auto()
    SUCCESS = auto()
    ERROR = auto()

class OutputType(Enum):
    TEXT = "text"
    TABLE = "table"
    ERROR = "error"
    HTML = "html"


@dataclass
class FizzNotebookConfig:
    max_cells: int = 1000
    auto_save: bool = True
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class CellOutput:
    output_type: OutputType = OutputType.TEXT
    text: str = ""
    data: Any = None

@dataclass
class Cell:
    cell_id: str = ""
    cell_type: CellType = CellType.CODE
    source: str = ""
    outputs: List[CellOutput] = field(default_factory=list)
    status: CellStatus = CellStatus.IDLE
    execution_count: Optional[int] = None
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Notebook:
    name: str = ""
    cells: List[Cell] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    version: str = "1.0"
    checkpoints: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class KernelSession:
    session_id: str = ""
    notebook_name: str = ""
    namespace: Dict[str, Any] = field(default_factory=dict)
    execution_counter: int = 0
    started_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    alive: bool = True

@dataclass
class NotebookMetrics:
    notebooks_created: int = 0
    cells_executed: int = 0
    total_execution_ms: float = 0.0
    active_kernels: int = 0
    exports: int = 0
    checkpoints: int = 0


# ============================================================
# Kernel
# ============================================================

class NotebookKernel:
    """FizzLang execution kernel with persistent namespace."""

    def __init__(self) -> None:
        self._sessions: Dict[str, KernelSession] = {}

    def create_session(self, notebook_name: str) -> KernelSession:
        session = KernelSession(
            session_id=uuid.uuid4().hex[:12],
            notebook_name=notebook_name,
            started_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
            namespace={"__fizzbuzz__": True},
        )
        self._sessions[session.session_id] = session
        return session

    def execute(self, session: KernelSession, source: str) -> List[CellOutput]:
        """Execute code in the kernel session. Returns outputs."""
        session.execution_counter += 1
        session.last_activity = datetime.now(timezone.utc)
        source = source.strip()

        # Handle magic commands
        if source.startswith("%"):
            return self._handle_magic(session, source)

        # Handle FizzBuzz evaluations
        if source.startswith("fizzbuzz(") or source.startswith("fizzbuzz "):
            return self._eval_fizzbuzz(session, source)

        # Handle variable assignment
        if "=" in source and not source.startswith("="):
            parts = source.split("=", 1)
            var_name = parts[0].strip()
            value_expr = parts[1].strip()
            try:
                value = self._eval_expression(session, value_expr)
                session.namespace[var_name] = value
                return [CellOutput(OutputType.TEXT, f"{var_name} = {value}")]
            except Exception as e:
                return [CellOutput(OutputType.ERROR, str(e))]

        # Handle expressions
        try:
            result = self._eval_expression(session, source)
            if result is not None:
                session.namespace["_"] = result
                return [CellOutput(OutputType.TEXT, str(result))]
            return []
        except Exception as e:
            return [CellOutput(OutputType.ERROR, f"Error: {e}")]

    def _eval_fizzbuzz(self, session: KernelSession, source: str) -> List[CellOutput]:
        """Evaluate FizzBuzz expressions."""
        # Extract number(s)
        import re
        numbers = re.findall(r'\d+', source)
        if not numbers:
            return [CellOutput(OutputType.ERROR, "fizzbuzz requires a number or range")]

        if "range" in source or ".." in source or len(numbers) >= 2:
            start = int(numbers[0])
            end = int(numbers[1]) if len(numbers) > 1 else start + 10
            results = []
            for n in range(start, end + 1):
                if n % 15 == 0: results.append(f"{n}: FizzBuzz")
                elif n % 3 == 0: results.append(f"{n}: Fizz")
                elif n % 5 == 0: results.append(f"{n}: Buzz")
                else: results.append(f"{n}: {n}")
            return [CellOutput(OutputType.TEXT, "\n".join(results))]
        else:
            n = int(numbers[0])
            if n % 15 == 0: r = "FizzBuzz"
            elif n % 3 == 0: r = "Fizz"
            elif n % 5 == 0: r = "Buzz"
            else: r = str(n)
            session.namespace["_"] = r
            return [CellOutput(OutputType.TEXT, r)]

    def _eval_expression(self, session: KernelSession, expr: str) -> Any:
        """Evaluate a simple expression in the kernel namespace."""
        expr = expr.strip()
        if not expr:
            return None
        # Check namespace
        if expr in session.namespace:
            return session.namespace[expr]
        # Try numeric
        try:
            return int(expr)
        except ValueError:
            pass
        try:
            return float(expr)
        except ValueError:
            pass
        # String literal
        if (expr.startswith('"') and expr.endswith('"')) or (expr.startswith("'") and expr.endswith("'")):
            return expr[1:-1]
        # Simple arithmetic
        for op in ["+", "-", "*", "/", "%"]:
            if op in expr:
                parts = expr.rsplit(op, 1)
                left = self._eval_expression(session, parts[0])
                right = self._eval_expression(session, parts[1])
                if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                    if op == "+": return left + right
                    elif op == "-": return left - right
                    elif op == "*": return left * right
                    elif op == "/" and right != 0: return left / right
                    elif op == "%" and right != 0: return left % right
        return expr

    def _handle_magic(self, session: KernelSession, source: str) -> List[CellOutput]:
        """Handle magic commands."""
        parts = source.split(None, 1)
        magic = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        if magic == "%fizzbuzz":
            return self._eval_fizzbuzz(session, f"fizzbuzz({args})")
        elif magic == "%who":
            user_vars = {k: type(v).__name__ for k, v in session.namespace.items()
                         if not k.startswith("_")}
            lines = [f"  {k}: {t}" for k, t in sorted(user_vars.items())]
            return [CellOutput(OutputType.TEXT, "Variables:\n" + "\n".join(lines) if lines else "No variables")]
        elif magic == "%reset":
            session.namespace = {"__fizzbuzz__": True}
            session.execution_counter = 0
            return [CellOutput(OutputType.TEXT, "Kernel namespace reset")]
        elif magic == "%time":
            start = time.time()
            outputs = self.execute(session, args)
            elapsed = (time.time() - start) * 1000
            outputs.append(CellOutput(OutputType.TEXT, f"Wall time: {elapsed:.2f}ms"))
            return outputs
        elif magic == "%whos":
            user_vars = {k: (type(v).__name__, repr(v)[:50]) for k, v in session.namespace.items()
                         if not k.startswith("_")}
            lines = [f"  {k:<15} {t:<10} {r}" for k, (t, r) in sorted(user_vars.items())]
            header = f"  {'Variable':<15} {'Type':<10} Value"
            return [CellOutput(OutputType.TEXT, header + "\n" + "\n".join(lines) if lines else "No variables")]
        else:
            return [CellOutput(OutputType.ERROR, f"Unknown magic: {magic}")]

    def get_session(self, session_id: str) -> Optional[KernelSession]:
        return self._sessions.get(session_id)

    def shutdown_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            session.alive = False

    @property
    def active_sessions(self) -> int:
        return sum(1 for s in self._sessions.values() if s.alive)


# ============================================================
# Notebook Manager
# ============================================================

class NotebookManager:
    """Manages notebook lifecycle, storage, and operations."""

    def __init__(self, config: FizzNotebookConfig, kernel: NotebookKernel) -> None:
        self._config = config
        self._kernel = kernel
        self._notebooks: Dict[str, Notebook] = {}
        self._sessions: Dict[str, KernelSession] = {}
        self._metrics = NotebookMetrics()

    def create_notebook(self, name: str) -> Notebook:
        if name in self._notebooks:
            raise FizzNotebookExistsError(name)
        now = datetime.now(timezone.utc)
        nb = Notebook(name=name, created_at=now, modified_at=now,
                      metadata={"kernel": "fizzbuzz", "language": "FizzLang"})
        self._notebooks[name] = nb
        self._metrics.notebooks_created += 1
        # Create kernel session
        session = self._kernel.create_session(name)
        self._sessions[name] = session
        self._metrics.active_kernels = self._kernel.active_sessions
        return nb

    def get_notebook(self, name: str) -> Notebook:
        nb = self._notebooks.get(name)
        if nb is None:
            raise FizzNotebookNotFoundError(name)
        return nb

    def delete_notebook(self, name: str) -> None:
        if name not in self._notebooks:
            raise FizzNotebookNotFoundError(name)
        del self._notebooks[name]
        session = self._sessions.pop(name, None)
        if session:
            self._kernel.shutdown_session(session.session_id)

    def list_notebooks(self) -> List[Notebook]:
        return list(self._notebooks.values())

    def add_cell(self, notebook_name: str, cell_type: CellType = CellType.CODE,
                 source: str = "", position: int = -1) -> Cell:
        nb = self.get_notebook(notebook_name)
        cell = Cell(cell_id=uuid.uuid4().hex[:8], cell_type=cell_type, source=source)
        if position < 0 or position >= len(nb.cells):
            nb.cells.append(cell)
        else:
            nb.cells.insert(position, cell)
        nb.modified_at = datetime.now(timezone.utc)
        return cell

    def delete_cell(self, notebook_name: str, cell_id: str) -> None:
        nb = self.get_notebook(notebook_name)
        nb.cells = [c for c in nb.cells if c.cell_id != cell_id]
        nb.modified_at = datetime.now(timezone.utc)

    def execute_cell(self, notebook_name: str, cell_id: str) -> Cell:
        nb = self.get_notebook(notebook_name)
        cell = None
        for c in nb.cells:
            if c.cell_id == cell_id:
                cell = c
                break
        if cell is None:
            raise FizzNotebookCellError(cell_id, "Cell not found")
        if cell.cell_type != CellType.CODE:
            return cell

        session = self._sessions.get(notebook_name)
        if session is None:
            session = self._kernel.create_session(notebook_name)
            self._sessions[notebook_name] = session

        cell.status = CellStatus.RUNNING
        start = time.time()
        cell.outputs = self._kernel.execute(session, cell.source)
        cell.execution_time_ms = (time.time() - start) * 1000
        cell.execution_count = session.execution_counter

        has_error = any(o.output_type == OutputType.ERROR for o in cell.outputs)
        cell.status = CellStatus.ERROR if has_error else CellStatus.SUCCESS

        nb.modified_at = datetime.now(timezone.utc)
        self._metrics.cells_executed += 1
        self._metrics.total_execution_ms += cell.execution_time_ms
        return cell

    def execute_all(self, notebook_name: str) -> List[Cell]:
        nb = self.get_notebook(notebook_name)
        results = []
        for cell in nb.cells:
            if cell.cell_type == CellType.CODE:
                self.execute_cell(notebook_name, cell.cell_id)
            results.append(cell)
        return results

    def checkpoint(self, notebook_name: str) -> int:
        nb = self.get_notebook(notebook_name)
        cp = {"cells": [{"id": c.cell_id, "source": c.source, "type": c.cell_type.value}
                         for c in nb.cells],
              "timestamp": datetime.now(timezone.utc).isoformat()}
        nb.checkpoints.append(cp)
        self._metrics.checkpoints += 1
        return len(nb.checkpoints)

    def export_html(self, notebook_name: str) -> str:
        nb = self.get_notebook(notebook_name)
        lines = [f"<html><head><title>{nb.name}</title></head><body>",
                 f"<h1>{nb.name}</h1>"]
        for cell in nb.cells:
            if cell.cell_type == CellType.MARKDOWN:
                lines.append(f"<div class='markdown'>{cell.source}</div>")
            elif cell.cell_type == CellType.CODE:
                lines.append(f"<div class='code'><pre>In [{cell.execution_count or ' '}]: {cell.source}</pre>")
                for out in cell.outputs:
                    lines.append(f"<pre class='output'>{out.text}</pre>")
                lines.append("</div>")
        lines.append("</body></html>")
        self._metrics.exports += 1
        return "\n".join(lines)

    def export_markdown(self, notebook_name: str) -> str:
        nb = self.get_notebook(notebook_name)
        lines = [f"# {nb.name}\n"]
        for cell in nb.cells:
            if cell.cell_type == CellType.MARKDOWN:
                lines.append(cell.source + "\n")
            elif cell.cell_type == CellType.CODE:
                lines.append(f"```fizzbuzz\n{cell.source}\n```\n")
                for out in cell.outputs:
                    if out.text:
                        lines.append(f"```\n{out.text}\n```\n")
        self._metrics.exports += 1
        return "\n".join(lines)

    def get_variables(self, notebook_name: str) -> Dict[str, Any]:
        session = self._sessions.get(notebook_name)
        if session is None:
            return {}
        return {k: v for k, v in session.namespace.items() if not k.startswith("_")}

    def get_metrics(self) -> NotebookMetrics:
        m = copy.copy(self._metrics)
        m.active_kernels = self._kernel.active_sessions
        return m


# ============================================================
# Dashboard
# ============================================================

class FizzNotebookDashboard:
    def __init__(self, manager: NotebookManager, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._manager = manager
        self._width = width

    def render(self) -> str:
        m = self._manager.get_metrics()
        lines = [
            "=" * self._width,
            "FizzNotebook Dashboard".center(self._width),
            "=" * self._width,
            f"  Version:       {FIZZNOTEBOOK_VERSION}",
            f"  Notebooks:     {len(self._manager.list_notebooks())}",
            f"  Cells Exec:    {m.cells_executed}",
            f"  Exec Time:     {m.total_execution_ms:.1f}ms",
            f"  Kernels:       {m.active_kernels}",
            f"  Exports:       {m.exports}",
            f"  Checkpoints:   {m.checkpoints}",
        ]
        for nb in self._manager.list_notebooks():
            code_cells = sum(1 for c in nb.cells if c.cell_type == CellType.CODE)
            md_cells = sum(1 for c in nb.cells if c.cell_type == CellType.MARKDOWN)
            lines.append(f"\n  {nb.name}: {code_cells} code, {md_cells} markdown cells")
        return "\n".join(lines)


# ============================================================
# Middleware
# ============================================================

class FizzNotebookMiddleware(IMiddleware):
    def __init__(self, manager: NotebookManager, dashboard: FizzNotebookDashboard,
                 config: FizzNotebookConfig) -> None:
        self._manager = manager
        self._dashboard = dashboard
        self._config = config

    def get_name(self) -> str: return "fizznotebook"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: ProcessingContext, next_handler: Any) -> ProcessingContext:
        m = self._manager.get_metrics()
        context.metadata["fizznotebook_version"] = FIZZNOTEBOOK_VERSION
        context.metadata["fizznotebook_notebooks"] = len(self._manager.list_notebooks())
        context.metadata["fizznotebook_cells_executed"] = m.cells_executed
        if next_handler: return next_handler(context)
        return context

    def render_dashboard(self) -> str: return self._dashboard.render()

    def render_status(self) -> str:
        m = self._manager.get_metrics()
        return (f"FizzNotebook {FIZZNOTEBOOK_VERSION} | "
                f"Notebooks: {len(self._manager.list_notebooks())} | "
                f"Cells: {m.cells_executed} | Kernels: {m.active_kernels}")

    def render_list(self) -> str:
        nbs = self._manager.list_notebooks()
        lines = ["FizzNotebook Listing:"]
        for nb in nbs:
            lines.append(f"  {nb.name}: {len(nb.cells)} cells, modified {nb.modified_at}")
        if not nbs:
            lines.append("  (no notebooks)")
        return "\n".join(lines)

    def render_run(self, name: str) -> str:
        try:
            cells = self._manager.execute_all(name)
            lines = [f"FizzNotebook Run: {name}"]
            for cell in cells:
                if cell.cell_type == CellType.CODE:
                    lines.append(f"\n  In [{cell.execution_count}]: {cell.source}")
                    for out in cell.outputs:
                        lines.append(f"  Out: {out.text}")
                elif cell.cell_type == CellType.MARKDOWN:
                    lines.append(f"\n  {cell.source}")
            return "\n".join(lines)
        except FizzNotebookError as e:
            return f"Error: {e}"


# ============================================================
# Factory
# ============================================================

def create_fizznotebook_subsystem(
    max_cells: int = 1000,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[NotebookManager, FizzNotebookDashboard, FizzNotebookMiddleware]:
    config = FizzNotebookConfig(max_cells=max_cells, dashboard_width=dashboard_width)
    kernel = NotebookKernel()
    manager = NotebookManager(config, kernel)

    # Create a default notebook with FizzBuzz examples
    nb = manager.create_notebook("FizzBuzz Exploration")
    manager.add_cell("FizzBuzz Exploration", CellType.MARKDOWN,
                     "# FizzBuzz Exploration\nInteractive evaluation of the FizzBuzz classification function.")
    manager.add_cell("FizzBuzz Exploration", CellType.CODE, "fizzbuzz(15)")
    manager.add_cell("FizzBuzz Exploration", CellType.CODE, "fizzbuzz(range 1 20)")
    manager.add_cell("FizzBuzz Exploration", CellType.CODE, "x = 42")
    manager.add_cell("FizzBuzz Exploration", CellType.CODE, "x % 3")
    manager.add_cell("FizzBuzz Exploration", CellType.MARKDOWN,
                     "## Conclusion\nThe Enterprise FizzBuzz Platform correctly classifies all integers.")

    # Execute the default notebook
    manager.execute_all("FizzBuzz Exploration")

    dashboard = FizzNotebookDashboard(manager, dashboard_width)
    middleware = FizzNotebookMiddleware(manager, dashboard, config)

    logger.info("FizzNotebook initialized: 1 default notebook")
    return manager, dashboard, middleware

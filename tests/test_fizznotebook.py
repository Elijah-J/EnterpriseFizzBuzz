"""Tests for enterprise_fizzbuzz.infrastructure.fizznotebook"""
from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from enterprise_fizzbuzz.infrastructure.fizznotebook import (
    FIZZNOTEBOOK_VERSION, MIDDLEWARE_PRIORITY, CellType, CellStatus, OutputType,
    FizzNotebookConfig, Cell, Notebook, CellOutput,
    NotebookKernel, NotebookManager, FizzNotebookDashboard,
    FizzNotebookMiddleware, create_fizznotebook_subsystem,
)

@pytest.fixture
def subsystem():
    return create_fizznotebook_subsystem()

@pytest.fixture
def manager():
    m, _, _ = create_fizznotebook_subsystem()
    return m


class TestNotebookKernel:
    def test_fizzbuzz_eval(self):
        k = NotebookKernel()
        s = k.create_session("test")
        outputs = k.execute(s, "fizzbuzz(15)")
        assert any("FizzBuzz" in o.text for o in outputs)

    def test_fizzbuzz_range(self):
        k = NotebookKernel()
        s = k.create_session("test")
        outputs = k.execute(s, "fizzbuzz(range 1 5)")
        assert any("Fizz" in o.text for o in outputs)

    def test_variable_assignment(self):
        k = NotebookKernel()
        s = k.create_session("test")
        k.execute(s, "x = 42")
        assert s.namespace["x"] == 42

    def test_expression_eval(self):
        k = NotebookKernel()
        s = k.create_session("test")
        outputs = k.execute(s, "3 + 4")
        assert any("7" in o.text for o in outputs)

    def test_magic_who(self):
        k = NotebookKernel()
        s = k.create_session("test")
        k.execute(s, "x = 10")
        outputs = k.execute(s, "%who")
        assert any("x" in o.text for o in outputs)

    def test_magic_reset(self):
        k = NotebookKernel()
        s = k.create_session("test")
        k.execute(s, "x = 10")
        k.execute(s, "%reset")
        assert "x" not in s.namespace

    def test_magic_fizzbuzz(self):
        k = NotebookKernel()
        s = k.create_session("test")
        outputs = k.execute(s, "%fizzbuzz 9")
        assert any("Fizz" in o.text for o in outputs)

    def test_string_literal(self):
        k = NotebookKernel()
        s = k.create_session("test")
        outputs = k.execute(s, '"hello"')
        assert any("hello" in o.text for o in outputs)

    def test_unknown_magic(self):
        k = NotebookKernel()
        s = k.create_session("test")
        outputs = k.execute(s, "%nonexistent")
        assert any(o.output_type == OutputType.ERROR for o in outputs)

    def test_execution_counter(self):
        k = NotebookKernel()
        s = k.create_session("test")
        k.execute(s, "1")
        k.execute(s, "2")
        assert s.execution_counter == 2


class TestNotebookManager:
    def test_create_notebook(self):
        k = NotebookKernel()
        m = NotebookManager(FizzNotebookConfig(), k)
        nb = m.create_notebook("test")
        assert nb.name == "test"

    def test_create_duplicate(self):
        k = NotebookKernel()
        m = NotebookManager(FizzNotebookConfig(), k)
        m.create_notebook("test")
        with pytest.raises(Exception):
            m.create_notebook("test")

    def test_delete_notebook(self):
        k = NotebookKernel()
        m = NotebookManager(FizzNotebookConfig(), k)
        m.create_notebook("test")
        m.delete_notebook("test")
        with pytest.raises(Exception):
            m.get_notebook("test")

    def test_add_cell(self):
        k = NotebookKernel()
        m = NotebookManager(FizzNotebookConfig(), k)
        m.create_notebook("test")
        cell = m.add_cell("test", CellType.CODE, "fizzbuzz(15)")
        assert cell.source == "fizzbuzz(15)"

    def test_delete_cell(self):
        k = NotebookKernel()
        m = NotebookManager(FizzNotebookConfig(), k)
        m.create_notebook("test")
        cell = m.add_cell("test", CellType.CODE, "x = 1")
        m.delete_cell("test", cell.cell_id)
        nb = m.get_notebook("test")
        assert len(nb.cells) == 0

    def test_execute_cell(self):
        k = NotebookKernel()
        m = NotebookManager(FizzNotebookConfig(), k)
        m.create_notebook("test")
        cell = m.add_cell("test", CellType.CODE, "fizzbuzz(15)")
        result = m.execute_cell("test", cell.cell_id)
        assert result.status == CellStatus.SUCCESS
        assert any("FizzBuzz" in o.text for o in result.outputs)

    def test_execute_all(self):
        k = NotebookKernel()
        m = NotebookManager(FizzNotebookConfig(), k)
        m.create_notebook("test")
        m.add_cell("test", CellType.CODE, "fizzbuzz(3)")
        m.add_cell("test", CellType.CODE, "fizzbuzz(5)")
        results = m.execute_all("test")
        assert len(results) == 2

    def test_checkpoint(self):
        k = NotebookKernel()
        m = NotebookManager(FizzNotebookConfig(), k)
        m.create_notebook("test")
        m.add_cell("test", CellType.CODE, "x = 1")
        cp = m.checkpoint("test")
        assert cp == 1

    def test_export_html(self):
        k = NotebookKernel()
        m = NotebookManager(FizzNotebookConfig(), k)
        m.create_notebook("test")
        m.add_cell("test", CellType.CODE, "fizzbuzz(15)")
        m.execute_all("test")
        html = m.export_html("test")
        assert "<html>" in html
        assert "FizzBuzz" in html

    def test_export_markdown(self):
        k = NotebookKernel()
        m = NotebookManager(FizzNotebookConfig(), k)
        m.create_notebook("test")
        m.add_cell("test", CellType.MARKDOWN, "# Title")
        m.add_cell("test", CellType.CODE, "fizzbuzz(15)")
        m.execute_all("test")
        md = m.export_markdown("test")
        assert "# Title" in md
        assert "fizzbuzz" in md

    def test_get_variables(self):
        k = NotebookKernel()
        m = NotebookManager(FizzNotebookConfig(), k)
        m.create_notebook("test")
        m.add_cell("test", CellType.CODE, "x = 42")
        m.execute_all("test")
        vars = m.get_variables("test")
        assert vars.get("x") == 42

    def test_default_notebook_exists(self, manager):
        nbs = manager.list_notebooks()
        assert any(nb.name == "FizzBuzz Exploration" for nb in nbs)

    def test_metrics(self, manager):
        m = manager.get_metrics()
        assert m.cells_executed >= 4  # Default notebook cells


class TestFizzNotebookMiddleware:
    def test_get_name(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_name() == "fizznotebook"

    def test_get_priority(self, subsystem):
        _, _, mw = subsystem
        assert mw.get_priority() == MIDDLEWARE_PRIORITY

    def test_process(self, subsystem):
        _, _, mw = subsystem
        ctx = MagicMock(); ctx.metadata = {}
        mw.process(ctx, None)
        assert ctx.metadata["fizznotebook_version"] == FIZZNOTEBOOK_VERSION

    def test_render_dashboard(self, subsystem):
        _, _, mw = subsystem
        assert "FizzNotebook" in mw.render_dashboard()

    def test_render_list(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_list()
        assert "FizzBuzz Exploration" in output

    def test_render_run(self, subsystem):
        _, _, mw = subsystem
        output = mw.render_run("FizzBuzz Exploration")
        assert "FizzBuzz" in output


class TestCreateSubsystem:
    def test_returns_tuple(self):
        assert len(create_fizznotebook_subsystem()) == 3

    def test_default_notebook(self):
        m, _, _ = create_fizznotebook_subsystem()
        assert len(m.list_notebooks()) == 1


class TestConstants:
    def test_version(self):
        assert FIZZNOTEBOOK_VERSION == "1.0.0"
    def test_priority(self):
        assert MIDDLEWARE_PRIORITY == 136

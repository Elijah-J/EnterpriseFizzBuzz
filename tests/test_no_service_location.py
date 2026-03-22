"""
Enterprise FizzBuzz Platform - Service Location Anti-Pattern Guard

AST-based test that ensures ``container.resolve()`` calls only appear in
the composition root (``__main__.py``) and test files. If ``resolve()``
leaks into domain, application, or infrastructure modules, it means
someone is using the Service Locator anti-pattern instead of proper
constructor injection, and that is a Clean Architecture violation
punishable by mandatory reading of Mark Seemann's "Dependency Injection
in .NET" (all 584 pages).

The composition root is the ONE place where the container is allowed
to resolve services. Everywhere else, dependencies should flow inward
via constructor parameters, not be yanked out of a global container
like candy from a pinata.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
PACKAGE_DIR = PROJECT_ROOT / "enterprise_fizzbuzz"

# Files where container.resolve() is ALLOWED
ALLOWED_FILES = {
    "__main__.py",
}


def _get_resolve_calls(filepath: Path) -> list[tuple[int, str]]:
    """Find all ``*.resolve(`` calls in a Python file via AST inspection.

    Returns (line_number, source_snippet) tuples for each violation.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    violations: list[tuple[int, str]] = []
    source_lines = source.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Match pattern: <something>.resolve(...)
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "resolve"
            ):
                # Check if receiver name contains "container"
                if isinstance(func.value, ast.Name) and "container" in func.value.id.lower():
                    line = source_lines[node.lineno - 1].strip() if node.lineno <= len(source_lines) else "?"
                    violations.append((node.lineno, line))

    return violations


def _get_python_files_recursive(directory: Path) -> list[Path]:
    """Get all .py files recursively, excluding __init__.py and test files."""
    if not directory.exists():
        return []
    return [
        f for f in directory.rglob("*.py")
        if f.name != "__init__.py"
    ]


class TestNoServiceLocation:
    """Verify that container.resolve() only appears in the composition root.

    The Service Locator pattern is the evil twin of Dependency Injection.
    Both provide dependencies, but Service Locator hides them inside
    method bodies where they're invisible to callers, untestable without
    the container, and generally a nightmare for anyone trying to
    understand what a class actually needs.

    This test ensures that ``container.resolve()`` calls only appear in
    ``__main__.py`` (the composition root), where they belong.
    """

    @pytest.fixture
    def package_files(self) -> list[Path]:
        """All Python files in the enterprise_fizzbuzz package."""
        return _get_python_files_recursive(PACKAGE_DIR)

    def test_resolve_only_in_composition_root(self, package_files: list[Path]) -> None:
        """container.resolve() must only appear in __main__.py."""
        violations = []
        for filepath in package_files:
            if filepath.name in ALLOWED_FILES:
                continue
            for lineno, line in _get_resolve_calls(filepath):
                rel_path = filepath.relative_to(PROJECT_ROOT)
                violations.append(f"  {rel_path}:{lineno}  {line}")

        assert not violations, (
            "Service Locator anti-pattern detected! container.resolve() "
            "was found outside the composition root (__main__.py).\n"
            "Move these resolve() calls to __main__.py and inject "
            "dependencies via constructors instead.\n"
            "Violations:\n" + "\n".join(violations)
        )

"""
Enterprise FizzBuzz Platform - Architecture Compliance Tests

AST-based import linter that validates the domain layer has no
imports from the application or infrastructure layers, enforcing
Clean Architecture / Hexagonal Architecture dependency rules.

The domain layer is the innermost circle. It must not know about
configuration managers, formatters, observers, or any other
infrastructure concern. If models.py ever imports from config.py,
this test will catch it and shame it publicly.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# Layer directories
DOMAIN_DIR = PROJECT_ROOT / "enterprise_fizzbuzz" / "domain"
APPLICATION_DIR = PROJECT_ROOT / "enterprise_fizzbuzz" / "application"
INFRASTRUCTURE_DIR = PROJECT_ROOT / "enterprise_fizzbuzz" / "infrastructure"

# Forbidden import prefixes for domain layer
DOMAIN_FORBIDDEN_PREFIXES = (
    "enterprise_fizzbuzz.application",
    "enterprise_fizzbuzz.infrastructure",
)

# Forbidden import prefixes for application layer
APPLICATION_FORBIDDEN_PREFIXES = (
    "enterprise_fizzbuzz.infrastructure",
)


def _get_imports_from_file(filepath: Path) -> list[tuple[int, str]]:
    """Parse a Python file and return all import module paths with line numbers.

    Returns:
        List of (line_number, module_path) tuples.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=str(filepath))
        except SyntaxError:
            return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append((node.lineno, node.module))

    return imports


def _get_python_files(directory: Path) -> list[Path]:
    """Get all .py files in a directory."""
    if not directory.exists():
        return []
    return [
        f for f in directory.iterdir()
        if f.is_file() and f.suffix == ".py" and f.name != "__init__.py"
    ]


class TestDomainLayerPurity:
    """Verify that the domain layer has no dependencies on outer layers.

    In Clean Architecture, the domain layer is sacred ground. It contains
    only pure domain logic -- models, exceptions, and interface contracts.
    It must never import from application or infrastructure layers.
    """

    @pytest.fixture
    def domain_files(self) -> list[Path]:
        return _get_python_files(DOMAIN_DIR)

    def test_domain_files_exist(self, domain_files: list[Path]) -> None:
        """Verify domain layer contains expected files."""
        filenames = {f.name for f in domain_files}
        assert "models.py" in filenames, "Domain layer must contain models.py"
        assert "exceptions.py" in filenames, "Domain layer must contain exceptions.py"
        assert "interfaces.py" in filenames, "Domain layer must contain interfaces.py"

    def test_domain_does_not_import_application(self, domain_files: list[Path]) -> None:
        """Domain layer must not import from application layer."""
        violations = []
        for filepath in domain_files:
            for lineno, module in _get_imports_from_file(filepath):
                if module.startswith("enterprise_fizzbuzz.application"):
                    violations.append(
                        f"  {filepath.name}:{lineno} imports {module}"
                    )

        assert not violations, (
            "Domain layer must not import from application layer.\n"
            "Violations found:\n" + "\n".join(violations)
        )

    def test_domain_does_not_import_infrastructure(self, domain_files: list[Path]) -> None:
        """Domain layer must not import from infrastructure layer."""
        violations = []
        for filepath in domain_files:
            for lineno, module in _get_imports_from_file(filepath):
                if module.startswith("enterprise_fizzbuzz.infrastructure"):
                    violations.append(
                        f"  {filepath.name}:{lineno} imports {module}"
                    )

        assert not violations, (
            "Domain layer must not import from infrastructure layer.\n"
            "Violations found:\n" + "\n".join(violations)
        )

    def test_domain_only_imports_domain_or_stdlib(self, domain_files: list[Path]) -> None:
        """Domain layer may only import from stdlib or its own domain package."""
        violations = []
        for filepath in domain_files:
            for lineno, module in _get_imports_from_file(filepath):
                # Allow stdlib and domain self-imports
                if module.startswith("enterprise_fizzbuzz."):
                    if not module.startswith("enterprise_fizzbuzz.domain"):
                        violations.append(
                            f"  {filepath.name}:{lineno} imports {module}"
                        )

        assert not violations, (
            "Domain layer may only import from stdlib or enterprise_fizzbuzz.domain.\n"
            "Violations found:\n" + "\n".join(violations)
        )


class TestPackageStructure:
    """Verify that the package structure exists and is well-formed."""

    def test_enterprise_fizzbuzz_package_exists(self) -> None:
        assert (PROJECT_ROOT / "enterprise_fizzbuzz" / "__init__.py").exists()

    def test_domain_package_exists(self) -> None:
        assert DOMAIN_DIR.exists()
        assert (DOMAIN_DIR / "__init__.py").exists()

    def test_application_package_exists(self) -> None:
        assert APPLICATION_DIR.exists()
        assert (APPLICATION_DIR / "__init__.py").exists()

    def test_infrastructure_package_exists(self) -> None:
        assert INFRASTRUCTURE_DIR.exists()
        assert (INFRASTRUCTURE_DIR / "__init__.py").exists()

    def test_domain_contains_expected_modules(self) -> None:
        expected = {"models.py", "exceptions.py", "interfaces.py"}
        actual = {f.name for f in _get_python_files(DOMAIN_DIR)}
        assert expected.issubset(actual), f"Missing domain modules: {expected - actual}"

    def test_application_contains_expected_modules(self) -> None:
        expected = {"factory.py", "fizzbuzz_service.py"}
        actual = {f.name for f in _get_python_files(APPLICATION_DIR)}
        assert expected.issubset(actual), f"Missing application modules: {expected - actual}"

    def test_infrastructure_contains_expected_modules(self) -> None:
        expected = {
            "config.py", "container.py", "formatters.py", "observers.py",
            "plugins.py", "rules_engine.py", "otel_tracing.py", "middleware.py",
            "auth.py", "blockchain.py", "cache.py", "chaos.py",
            "circuit_breaker.py", "event_sourcing.py", "feature_flags.py",
            "ml_engine.py", "sla.py", "migrations.py", "i18n.py",
        }
        actual = {f.name for f in _get_python_files(INFRASTRUCTURE_DIR)}
        assert expected.issubset(actual), f"Missing infrastructure modules: {expected - actual}"


class TestBackwardCompatibleStubs:
    """Verify that root-level stubs re-export correctly from the new package."""

    @pytest.mark.parametrize("module_name,symbol", [
        ("models", "FizzBuzzResult"),
        ("models", "EvaluationStrategy"),
        ("exceptions", "FizzBuzzError"),
        ("exceptions", "ConfigurationError"),
        ("interfaces", "IRule"),
        ("interfaces", "IRuleEngine"),
        ("config", "ConfigurationManager"),
        ("config", "_SingletonMeta"),
        ("i18n", "LocaleManager"),
        ("i18n", "TranslationService"),
        ("formatters", "FormatterFactory"),
        ("observers", "EventBus"),
        ("plugins", "PluginRegistry"),
        ("rules_engine", "ConcreteRule"),
        ("rules_engine", "RuleEngineFactory"),
        ("middleware", "MiddlewarePipeline"),
        ("middleware", "TranslationMiddleware"),
        ("auth", "AuthorizationMiddleware"),
        ("blockchain", "FizzBuzzBlockchain"),
        ("cache", "CacheStore"),
        ("chaos", "ChaosMonkey"),
        ("circuit_breaker", "CircuitBreakerMiddleware"),
        ("event_sourcing", "EventSourcingSystem"),
        ("feature_flags", "FlagStore"),
        ("ml_engine", "MachineLearningEngine"),
        ("sla", "SLAMonitor"),
        ("migrations", "MigrationRunner"),
        ("factory", "StandardRuleFactory"),
        ("fizzbuzz_service", "FizzBuzzServiceBuilder"),
    ])
    def test_stub_re_exports_symbol(self, module_name: str, symbol: str) -> None:
        """Verify that a root-level stub correctly re-exports a symbol."""
        import importlib
        mod = importlib.import_module(module_name)
        assert hasattr(mod, symbol), (
            f"Root stub '{module_name}' does not re-export '{symbol}'"
        )

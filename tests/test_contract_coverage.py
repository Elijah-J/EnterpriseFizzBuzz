"""
Enterprise FizzBuzz Platform - Contract Coverage Meta-Tests

The test that tests the tests. This architectural guardian ensures that
every port (abstract interface) in the application layer has corresponding
contract tests. Because untested contracts are just suggestions, and
suggestions are not enterprise-grade.

If you add a new port and forget to write contract tests, this file
will fail and shame you publicly in CI. Consider it an automated code
review from the architecture team, except it never goes on vacation
and it never accepts "I'll add tests later" as a valid excuse.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestContractCoverageCompleteness:
    """Meta-tests verifying that every architectural port has contract test coverage.

    This is the testing equivalent of an audit — boring, necessary, and
    deeply satisfying when everything passes.
    """

    def test_repository_contract_tests_exist(self) -> None:
        """Verify that the repository contract test module exists and defines tests."""
        from tests.contracts import test_repository_contract
        assert hasattr(test_repository_contract, "RepositoryContractTests")
        assert hasattr(test_repository_contract, "TestInMemoryRepositoryContract")
        assert hasattr(test_repository_contract, "TestSqliteRepositoryContract")
        assert hasattr(test_repository_contract, "TestFileSystemRepositoryContract")

    def test_strategy_contract_tests_exist(self) -> None:
        """Verify that the strategy contract test module exists and defines tests."""
        from tests.contracts import test_strategy_contract
        assert hasattr(test_strategy_contract, "StrategyContractTests")
        assert hasattr(test_strategy_contract, "TestStandardStrategyContract")
        assert hasattr(test_strategy_contract, "TestChainStrategyContract")
        assert hasattr(test_strategy_contract, "TestAsyncStrategyContract")
        assert hasattr(test_strategy_contract, "TestMLStrategyContract")

    def test_formatter_contract_tests_exist(self) -> None:
        """Verify that the formatter contract test module exists and defines tests."""
        from tests.contracts import test_formatter_contract
        assert hasattr(test_formatter_contract, "FormatterContractTests")
        assert hasattr(test_formatter_contract, "TestPlainTextFormatterContract")
        assert hasattr(test_formatter_contract, "TestJsonFormatterContract")
        assert hasattr(test_formatter_contract, "TestXmlFormatterContract")
        assert hasattr(test_formatter_contract, "TestCsvFormatterContract")

    def test_repository_mixin_not_collected_as_test(self) -> None:
        """The mixin class must NOT start with 'Test' to avoid pytest collection."""
        from tests.contracts.test_repository_contract import RepositoryContractTests
        assert not RepositoryContractTests.__name__.startswith("Test"), (
            "RepositoryContractTests starts with 'Test', which means pytest "
            "will try to collect it directly. Rename it or face the wrath "
            "of 'cannot instantiate abstract class'."
        )

    def test_strategy_mixin_not_collected_as_test(self) -> None:
        """The mixin class must NOT start with 'Test'."""
        from tests.contracts.test_strategy_contract import StrategyContractTests
        assert not StrategyContractTests.__name__.startswith("Test")

    def test_formatter_mixin_not_collected_as_test(self) -> None:
        """The mixin class must NOT start with 'Test'."""
        from tests.contracts.test_formatter_contract import FormatterContractTests
        assert not FormatterContractTests.__name__.startswith("Test")

    def test_all_repository_implementations_have_contracts(self) -> None:
        """Every AbstractRepository subclass in the codebase must have a contract test."""
        from enterprise_fizzbuzz.infrastructure.persistence.in_memory import InMemoryRepository
        from enterprise_fizzbuzz.infrastructure.persistence.sqlite import SqliteRepository
        from enterprise_fizzbuzz.infrastructure.persistence.filesystem import FileSystemRepository
        from tests.contracts.test_repository_contract import (
            TestInMemoryRepositoryContract,
            TestSqliteRepositoryContract,
            TestFileSystemRepositoryContract,
        )

        covered_impls = {
            InMemoryRepository: TestInMemoryRepositoryContract,
            SqliteRepository: TestSqliteRepositoryContract,
            FileSystemRepository: TestFileSystemRepositoryContract,
        }
        for impl_class, test_class in covered_impls.items():
            assert test_class is not None, (
                f"{impl_class.__name__} has no contract test class. "
                f"Every repository deserves equal representation under the law."
            )

    def test_all_strategy_implementations_have_contracts(self) -> None:
        """Every StrategyPort adapter must have a contract test."""
        from enterprise_fizzbuzz.infrastructure.adapters.strategy_adapters import (
            StandardStrategyAdapter,
            ChainStrategyAdapter,
            AsyncStrategyAdapter,
            MLStrategyAdapter,
        )
        from tests.contracts.test_strategy_contract import (
            TestStandardStrategyContract,
            TestChainStrategyContract,
            TestAsyncStrategyContract,
            TestMLStrategyContract,
        )

        covered_adapters = {
            StandardStrategyAdapter: TestStandardStrategyContract,
            ChainStrategyAdapter: TestChainStrategyContract,
            AsyncStrategyAdapter: TestAsyncStrategyContract,
            MLStrategyAdapter: TestMLStrategyContract,
        }
        for adapter_class, test_class in covered_adapters.items():
            assert test_class is not None, (
                f"{adapter_class.__name__} has no contract test class. "
                f"Unverified adapters are a liability."
            )

    def test_all_formatter_implementations_have_contracts(self) -> None:
        """Every IFormatter implementation must have a contract test."""
        from enterprise_fizzbuzz.infrastructure.formatters import (
            PlainTextFormatter,
            JsonFormatter,
            XmlFormatter,
            CsvFormatter,
        )
        from tests.contracts.test_formatter_contract import (
            TestPlainTextFormatterContract,
            TestJsonFormatterContract,
            TestXmlFormatterContract,
            TestCsvFormatterContract,
        )

        covered_formatters = {
            PlainTextFormatter: TestPlainTextFormatterContract,
            JsonFormatter: TestJsonFormatterContract,
            XmlFormatter: TestXmlFormatterContract,
            CsvFormatter: TestCsvFormatterContract,
        }
        for fmt_class, test_class in covered_formatters.items():
            assert test_class is not None, (
                f"{fmt_class.__name__} has no contract test. "
                f"A formatter without a contract is just free text."
            )

    def test_middleware_contract_tests_exist(self) -> None:
        """Verify that the middleware contract test module exists and defines tests."""
        from tests.contracts import test_middleware_contract
        assert hasattr(test_middleware_contract, "TestMiddlewareDiscovery")
        assert hasattr(test_middleware_contract, "TestMiddlewareGetNameContract")
        assert hasattr(test_middleware_contract, "TestMiddlewareGetPriorityContract")
        assert hasattr(test_middleware_contract, "TestMiddlewareProcessContract")
        assert hasattr(test_middleware_contract, "TestMiddlewareIsIMiddleware")
        assert hasattr(test_middleware_contract, "TestMiddlewarePipelineConsistency")

    def test_engine_contract_tests_exist(self) -> None:
        """Verify that the engine contract test module exists and defines tests."""
        from tests.contracts import test_engine_contract
        assert hasattr(test_engine_contract, "TestEngineDiscovery")
        assert hasattr(test_engine_contract, "TestEngineEvaluationContract")
        assert hasattr(test_engine_contract, "TestEngineConsistency")
        assert hasattr(test_engine_contract, "TestEngineIsIRuleEngine")

    def test_middleware_contract_dynamically_discovers_implementations(self) -> None:
        """The middleware contract suite must discover at least 20 IMiddleware implementations."""
        from tests.contracts.test_middleware_contract import ALL_MIDDLEWARE_CLASSES
        assert len(ALL_MIDDLEWARE_CLASSES) >= 20, (
            f"Middleware contract suite discovered only {len(ALL_MIDDLEWARE_CLASSES)} "
            f"implementations. Expected at least 20. The discovery engine is "
            f"underperforming."
        )

    def test_engine_contract_dynamically_discovers_implementations(self) -> None:
        """The engine contract suite must discover at least 4 IRuleEngine implementations."""
        from tests.contracts.test_engine_contract import ALL_ENGINE_CLASSES
        assert len(ALL_ENGINE_CLASSES) >= 4, (
            f"Engine contract suite discovered only {len(ALL_ENGINE_CLASSES)} "
            f"implementations. Expected at least 4. The discovery engine is "
            f"not trying hard enough."
        )

    def test_all_iruleengine_implementations_have_contracts(self) -> None:
        """Every IRuleEngine implementation must be covered by contract tests."""
        from enterprise_fizzbuzz.infrastructure.rules_engine import (
            StandardRuleEngine,
            ChainOfResponsibilityEngine,
            ParallelAsyncEngine,
        )
        from enterprise_fizzbuzz.infrastructure.ml_engine import MachineLearningEngine
        from tests.contracts.test_engine_contract import ALL_ENGINE_CLASSES

        expected_engines = {
            StandardRuleEngine,
            ChainOfResponsibilityEngine,
            ParallelAsyncEngine,
            MachineLearningEngine,
        }
        discovered = set(ALL_ENGINE_CLASSES)
        missing = expected_engines - discovered
        assert not missing, (
            f"The following engines have no contract coverage: "
            f"{[c.__name__ for c in missing]}. "
            f"Engines without contracts are a danger to the platform."
        )

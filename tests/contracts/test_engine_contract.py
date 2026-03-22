"""
Enterprise FizzBuzz Platform - Rule Engine Contract Tests

Defines the behavioral contract that every IRuleEngine implementation must
satisfy. Whether the engine evaluates rules via sequential iteration, a
Chain of Responsibility, parallel async coroutines, or a from-scratch neural
network, the contract is unambiguous: evaluate(15) is "FizzBuzz",
evaluate(3) is "Fizz", evaluate(5) is "Buzz", and evaluate(7) is "7".

If your engine disagrees with these fundamental truths, it is not a valid
IRuleEngine — it is a random number generator with delusions of grandeur.

The EngineContractTests mixin discovers all IRuleEngine implementations
dynamically, because if someone adds a QuantumEntangledBayesianEngine
and forgets to verify it can correctly compute 15 % 3, the contract
tests will catch it before production does.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
from abc import abstractmethod
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from enterprise_fizzbuzz.domain.interfaces import IRule, IRuleEngine
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    RuleDefinition,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule


# ============================================================
# Dynamic Discovery Engine
# ============================================================


def _discover_engine_classes() -> list[type]:
    """Crawl the infrastructure package and return every IRuleEngine subclass.

    The search is exhaustive: every .py file in the infrastructure package
    and its subpackages is inspected. If you've hidden an IRuleEngine
    implementation in a file called `definitely_not_a_rule_engine.py`,
    this function will find it anyway.
    """
    import enterprise_fizzbuzz.infrastructure as infra_pkg

    engine_classes: list[type] = []
    pkg_path = Path(infra_pkg.__file__).parent

    for importer, modname, ispkg in pkgutil.walk_packages(
        [str(pkg_path)],
        prefix="enterprise_fizzbuzz.infrastructure.",
    ):
        if ispkg:
            continue
        try:
            module = importlib.import_module(modname)
        except Exception:
            continue

        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, IRuleEngine)
                and obj is not IRuleEngine
                and not inspect.isabstract(obj)
                and obj.__module__ == module.__name__
            ):
                engine_classes.append(obj)

    return sorted(engine_classes, key=lambda c: c.__name__)


ALL_ENGINE_CLASSES = _discover_engine_classes()


# ============================================================
# Canonical Rule Set
# ============================================================


def _make_standard_rules() -> list[IRule]:
    """Create the two sacred rules upon which the entire enterprise is built.

    Three divides into Fizz, five divides into Buzz. Together they form
    FizzBuzz — the fundamental theorem of enterprise software engineering.
    These rules are immutable, canonical, and non-negotiable. Any engine
    that fails to correctly evaluate them has no place in this platform.
    """
    return [
        ConcreteRule(RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1)),
        ConcreteRule(RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2)),
    ]


def _try_instantiate_engine(cls: type) -> IRuleEngine | None:
    """Attempt to instantiate an IRuleEngine with no arguments.

    All known engine implementations (StandardRuleEngine,
    ChainOfResponsibilityEngine, ParallelAsyncEngine, MachineLearningEngine)
    have parameterless constructors. If a future engine requires constructor
    arguments, this function will gracefully return None and the test will
    be skipped with an apologetic message.
    """
    try:
        return cls()
    except Exception:
        return None


# ============================================================
# Fixture: Singleton Reset
# ============================================================


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons between tests.

    The ML engine in particular may cause singleton state accumulation.
    A clean singleton slate ensures that each test starts from the same
    pristine initial conditions, like the universe before the Big Bang
    but with more Python.
    """
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# ============================================================
# Contract Test: Discovery Sanity
# ============================================================


class TestEngineDiscovery:
    """Verify that the dynamic discovery engine found all IRuleEngine implementations.

    If this test reports fewer than four engines, either the codebase has
    regressed or the discovery logic has a defect. Four engines is the
    minimum for an enterprise-grade FizzBuzz platform: standard, chain,
    async, and ML. Anything fewer is just a hobby project.
    """

    def test_discovered_at_least_four_implementations(self) -> None:
        """The platform has four known IRuleEngine implementations."""
        assert len(ALL_ENGINE_CLASSES) >= 4, (
            f"Only discovered {len(ALL_ENGINE_CLASSES)} IRuleEngine implementations. "
            f"Expected at least 4 (Standard, Chain, Async, ML). "
            f"The engine fleet is understaffed."
        )

    def test_all_discovered_classes_are_iruleengine_subclasses(self) -> None:
        """Every discovered class must implement IRuleEngine."""
        for cls in ALL_ENGINE_CLASSES:
            assert issubclass(cls, IRuleEngine), (
                f"{cls.__name__} was discovered as an engine but does not "
                f"implement IRuleEngine. The discovery engine has been deceived."
            )

    def test_known_engines_are_discovered(self) -> None:
        """All four canonical engines must appear in the discovery results."""
        discovered_names = {cls.__name__ for cls in ALL_ENGINE_CLASSES}
        expected = {
            "StandardRuleEngine",
            "ChainOfResponsibilityEngine",
            "ParallelAsyncEngine",
            "MachineLearningEngine",
        }
        missing = expected - discovered_names
        assert not missing, (
            f"The following canonical engines were not discovered: {missing}. "
            f"This suggests a discovery bug or a catastrophic refactoring."
        )


# ============================================================
# Contract Tests: Core Evaluation Correctness
# ============================================================


class TestEngineEvaluationContract:
    """The non-negotiable behavioral contract for IRuleEngine.evaluate().

    Every engine must produce the same output for the same input.
    FizzBuzz is a deterministic function — there is exactly one correct
    answer for each number, and every engine must agree on it. If your
    ML engine says 15 is "Buzz", your ML engine is wrong, not the math.
    """

    @pytest.mark.parametrize(
        "engine_class",
        ALL_ENGINE_CLASSES,
        ids=lambda c: c.__name__,
    )
    def test_evaluate_fifteen_returns_fizzbuzz(self, engine_class: type) -> None:
        """evaluate(15) must return 'FizzBuzz'. This is the canonical test case.

        15 is divisible by both 3 and 5. The output must be "FizzBuzz".
        Not "Fizz", not "Buzz", not "15", not "NaN", not a philosophical
        treatise on the nature of divisibility. Just "FizzBuzz".
        """
        engine = _try_instantiate_engine(engine_class)
        if engine is None:
            pytest.skip(f"Cannot instantiate {engine_class.__name__}.")
        rules = _make_standard_rules()
        result = engine.evaluate(15, rules)
        assert isinstance(result, FizzBuzzResult), (
            f"{engine_class.__name__}.evaluate() returned "
            f"{type(result).__name__} instead of FizzBuzzResult."
        )
        assert result.output == "FizzBuzz", (
            f"{engine_class.__name__}.evaluate(15) returned '{result.output}' "
            f"instead of 'FizzBuzz'. Fifteen is the bridge between Fizz and Buzz. "
            f"To get this wrong is to deny the fundamental theorem of FizzBuzz."
        )

    @pytest.mark.parametrize(
        "engine_class",
        ALL_ENGINE_CLASSES,
        ids=lambda c: c.__name__,
    )
    def test_evaluate_three_returns_fizz(self, engine_class: type) -> None:
        """evaluate(3) must return 'Fizz'. The first commandment of FizzBuzz."""
        engine = _try_instantiate_engine(engine_class)
        if engine is None:
            pytest.skip(f"Cannot instantiate {engine_class.__name__}.")
        rules = _make_standard_rules()
        result = engine.evaluate(3, rules)
        assert result.output == "Fizz", (
            f"{engine_class.__name__}.evaluate(3) returned '{result.output}' "
            f"instead of 'Fizz'. Three divides by three. This is settled law."
        )

    @pytest.mark.parametrize(
        "engine_class",
        ALL_ENGINE_CLASSES,
        ids=lambda c: c.__name__,
    )
    def test_evaluate_five_returns_buzz(self, engine_class: type) -> None:
        """evaluate(5) must return 'Buzz'. The second commandment of FizzBuzz."""
        engine = _try_instantiate_engine(engine_class)
        if engine is None:
            pytest.skip(f"Cannot instantiate {engine_class.__name__}.")
        rules = _make_standard_rules()
        result = engine.evaluate(5, rules)
        assert result.output == "Buzz", (
            f"{engine_class.__name__}.evaluate(5) returned '{result.output}' "
            f"instead of 'Buzz'. Five divides by five. This is not ambiguous."
        )

    @pytest.mark.parametrize(
        "engine_class",
        ALL_ENGINE_CLASSES,
        ids=lambda c: c.__name__,
    )
    def test_evaluate_seven_returns_string_seven(self, engine_class: type) -> None:
        """evaluate(7) must return '7'. A plain number. No label. No ceremony."""
        engine = _try_instantiate_engine(engine_class)
        if engine is None:
            pytest.skip(f"Cannot instantiate {engine_class.__name__}.")
        rules = _make_standard_rules()
        result = engine.evaluate(7, rules)
        assert result.output == "7", (
            f"{engine_class.__name__}.evaluate(7) returned '{result.output}' "
            f"instead of '7'. Seven is not divisible by 3 or 5. It is "
            f"simply a prime number, living its best life."
        )

    @pytest.mark.parametrize(
        "engine_class",
        ALL_ENGINE_CLASSES,
        ids=lambda c: c.__name__,
    )
    def test_evaluate_returns_fizzbuzz_result(self, engine_class: type) -> None:
        """evaluate() must return a FizzBuzzResult, not a string or a dict."""
        engine = _try_instantiate_engine(engine_class)
        if engine is None:
            pytest.skip(f"Cannot instantiate {engine_class.__name__}.")
        rules = _make_standard_rules()
        result = engine.evaluate(1, rules)
        assert isinstance(result, FizzBuzzResult), (
            f"{engine_class.__name__}.evaluate() returned "
            f"{type(result).__name__} instead of FizzBuzzResult. "
            f"The contract is clear: evaluate() returns FizzBuzzResult. "
            f"Not str. Not dict. Not None. FizzBuzzResult."
        )

    @pytest.mark.parametrize(
        "engine_class",
        ALL_ENGINE_CLASSES,
        ids=lambda c: c.__name__,
    )
    def test_evaluate_result_number_matches_input(self, engine_class: type) -> None:
        """The result's number field must match the input number."""
        engine = _try_instantiate_engine(engine_class)
        if engine is None:
            pytest.skip(f"Cannot instantiate {engine_class.__name__}.")
        rules = _make_standard_rules()
        for number in [1, 3, 5, 7, 15, 42]:
            result = engine.evaluate(number, rules)
            assert result.number == number, (
                f"{engine_class.__name__}.evaluate({number}) returned a result "
                f"with number={result.number}. The engine appears to be "
                f"evaluating the wrong number, which is concerning."
            )


# ============================================================
# Contract Tests: Cross-Engine Consistency
# ============================================================


class TestEngineConsistency:
    """Cross-engine consistency verification.

    The entire premise of the Strategy Pattern is that you can swap
    strategies without changing behavior. If StandardRuleEngine and
    MachineLearningEngine produce different results for the same
    input, the Strategy Pattern has failed — and with it, the hopes
    and dreams of every software architect who put "Design Patterns"
    on their resume.
    """

    def test_all_engines_agree_on_range_1_to_100(self) -> None:
        """Every engine must produce identical results for numbers 1 through 100.

        This is the definitive cross-engine consistency check. One hundred
        numbers, evaluated by every available engine, all producing the
        same output. If even one engine disagrees on one number, the
        entire FizzBuzz platform's credibility is at stake.
        """
        rules = _make_standard_rules()
        engines: list[tuple[str, IRuleEngine]] = []

        for cls in ALL_ENGINE_CLASSES:
            engine = _try_instantiate_engine(cls)
            if engine is not None:
                engines.append((cls.__name__, engine))

        assert len(engines) >= 2, (
            "Cannot verify cross-engine consistency with fewer than 2 engines."
        )

        # Use the first engine as the reference implementation
        ref_name, ref_engine = engines[0]
        ref_results = {
            n: ref_engine.evaluate(n, rules).output
            for n in range(1, 101)
        }

        for engine_name, engine in engines[1:]:
            for n in range(1, 101):
                actual = engine.evaluate(n, rules).output
                expected = ref_results[n]
                assert actual == expected, (
                    f"Cross-engine inconsistency at number {n}: "
                    f"{ref_name} says '{expected}', but "
                    f"{engine_name} says '{actual}'. "
                    f"The Strategy Pattern weeps."
                )

    def test_all_engines_handle_fizzbuzz_multiples_correctly(self) -> None:
        """Every engine must correctly identify all FizzBuzz multiples up to 100.

        FizzBuzz multiples (15, 30, 45, 60, 75, 90) are the crown jewels
        of the FizzBuzz sequence. Getting any of them wrong would be like
        a calculator that can add but not multiply.
        """
        rules = _make_standard_rules()
        fizzbuzz_numbers = [n for n in range(1, 101) if n % 15 == 0]

        for cls in ALL_ENGINE_CLASSES:
            engine = _try_instantiate_engine(cls)
            if engine is None:
                continue
            for n in fizzbuzz_numbers:
                result = engine.evaluate(n, rules)
                assert result.output == "FizzBuzz", (
                    f"{cls.__name__}.evaluate({n}) returned '{result.output}' "
                    f"instead of 'FizzBuzz'. {n} is divisible by both 3 and 5. "
                    f"This is not debatable."
                )

    def test_all_engines_handle_plain_numbers_correctly(self) -> None:
        """Numbers not divisible by 3 or 5 must be returned as their string representation."""
        rules = _make_standard_rules()
        plain_numbers = [n for n in range(1, 101) if n % 3 != 0 and n % 5 != 0]

        for cls in ALL_ENGINE_CLASSES:
            engine = _try_instantiate_engine(cls)
            if engine is None:
                continue
            for n in plain_numbers:
                result = engine.evaluate(n, rules)
                assert result.output == str(n), (
                    f"{cls.__name__}.evaluate({n}) returned '{result.output}' "
                    f"instead of '{n}'. The number is not divisible by 3 or 5, "
                    f"so it should just be itself. Self-identity is not complicated."
                )


# ============================================================
# Contract Tests: Interface Compliance
# ============================================================


class TestEngineIsIRuleEngine:
    """Verify that every discovered class truly implements IRuleEngine."""

    @pytest.mark.parametrize(
        "engine_class",
        ALL_ENGINE_CLASSES,
        ids=lambda c: c.__name__,
    )
    def test_instance_is_iruleengine(self, engine_class: type) -> None:
        """An instance of the class must pass isinstance(x, IRuleEngine)."""
        engine = _try_instantiate_engine(engine_class)
        if engine is None:
            pytest.skip(f"Cannot instantiate {engine_class.__name__}.")
        assert isinstance(engine, IRuleEngine), (
            f"{engine_class.__name__} claims to be a rule engine but fails "
            f"isinstance(x, IRuleEngine). Claiming to be an engine without "
            f"implementing the interface is like putting 'CEO' on your "
            f"LinkedIn when you run a lemonade stand."
        )

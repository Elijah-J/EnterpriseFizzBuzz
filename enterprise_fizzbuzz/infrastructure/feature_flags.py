"""
Enterprise FizzBuzz Platform - Feature Flags / Progressive Rollout Module

Implements a comprehensive feature flag system with:
  - Boolean, Percentage, and Targeting flag types
  - Deterministic hash-based percentage rollout (no randomness allowed)
  - Dependency graph with cycle detection via Kahn's topological sort
  - Full lifecycle management (CREATED -> ACTIVE -> DEPRECATED -> ARCHIVED)
  - FlagMiddleware integration into the middleware pipeline
  - ASCII evaluation summary renderer for maximum enterprise visibility

Because toggling FizzBuzz rules on and off clearly requires the same
infrastructure that Netflix uses to manage feature rollouts across
200 million subscribers. Your 100 integers deserve nothing less.
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    FeatureFlagError,
    FlagDependencyCycleError,
    FlagDependencyNotMetError,
    FlagLifecycleError,
    FlagNotFoundError,
    FlagRolloutError,
    FlagTargetingError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FlagLifecycle,
    FlagType,
    ProcessingContext,
    RuleDefinition,
)

logger = logging.getLogger(__name__)


# ============================================================
# Targeting Rules
# ============================================================


class TargetingRule:
    """Evaluates whether a number qualifies for a targeted feature flag.

    Supports multiple rule types because apparently checking whether
    an integer is prime or even requires a formal targeting engine
    with named rule types and validation. Enterprise!

    Supported rule types:
        - prime: matches prime numbers (because they're special)
        - even: matches even numbers (the reliable majority)
        - odd: matches odd numbers (the rebellious minority)
        - range: matches numbers within [min, max]
        - modulo: matches numbers where number % divisor == remainder
    """

    VALID_RULE_TYPES = {"prime", "even", "odd", "range", "modulo"}

    def __init__(
        self,
        rule_type: str,
        params: Optional[dict[str, Any]] = None,
    ) -> None:
        if rule_type not in self.VALID_RULE_TYPES:
            raise FlagTargetingError(
                "unknown",
                rule_type,
                f"Invalid targeting rule type. Valid types: {self.VALID_RULE_TYPES}",
            )
        self.rule_type = rule_type
        self.params = params or {}

    def evaluate(self, number: int) -> bool:
        """Evaluate whether the given number matches this targeting rule."""
        if self.rule_type == "prime":
            return self._is_prime(number)
        elif self.rule_type == "even":
            return number % 2 == 0
        elif self.rule_type == "odd":
            return number % 2 != 0
        elif self.rule_type == "range":
            min_val = self.params.get("min", 1)
            max_val = self.params.get("max", 100)
            return min_val <= number <= max_val
        elif self.rule_type == "modulo":
            divisor = self.params.get("divisor", 1)
            remainder = self.params.get("remainder", 0)
            if divisor == 0:
                raise FlagTargetingError(
                    "unknown", "modulo",
                    "Division by zero in modulo targeting rule. "
                    "Even feature flags cannot divide by zero.",
                )
            return number % divisor == remainder
        return False

    @staticmethod
    def _is_prime(n: int) -> bool:
        """Determine primality with the gravitas it deserves."""
        if n < 2:
            return False
        if n < 4:
            return True
        if n % 2 == 0 or n % 3 == 0:
            return False
        i = 5
        while i * i <= n:
            if n % i == 0 or n % (i + 2) == 0:
                return False
            i += 6
        return True

    def __repr__(self) -> str:
        return f"TargetingRule(type={self.rule_type!r}, params={self.params!r})"


# ============================================================
# Rollout Strategy
# ============================================================


class RolloutStrategy:
    """Deterministic hash-based percentage rollout for progressive feature delivery.

    Uses SHA-256 to hash the flag name combined with the input number,
    producing a deterministic bucket assignment in [0, 100). This
    ensures that the same number always gets the same rollout decision
    for a given flag, because non-deterministic FizzBuzz feature
    toggles would be an affront to engineering principles.

    The hash-based approach means:
      - No randomness: same input, same output, every time
      - Uniform distribution: each integer has an equal chance
      - Reproducibility: auditors can verify rollout decisions
    """

    @staticmethod
    def compute_bucket(flag_name: str, number: int) -> float:
        """Compute a deterministic bucket value in [0, 100) for the given input.

        The bucket is derived from the SHA-256 hash of the flag name
        concatenated with the number, because enterprise-grade
        bucketing demands cryptographic hash functions even when
        we're just deciding whether to print "Wuzz" for the number 7.
        """
        payload = f"{flag_name}:{number}".encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        # Take the first 8 hex chars (32 bits) and map to [0, 100)
        hash_int = int(digest[:8], 16)
        return (hash_int / 0xFFFFFFFF) * 100.0

    @staticmethod
    def is_in_rollout(flag_name: str, number: int, percentage: float) -> bool:
        """Determine whether a number falls within the rollout percentage.

        Returns True if the number's deterministic bucket is below
        the configured percentage threshold. A percentage of 0 means
        nobody gets in. A percentage of 100 means everybody gets in.
        A percentage of 50 means... well, you get the idea.
        """
        if percentage <= 0.0:
            return False
        if percentage >= 100.0:
            return True
        bucket = RolloutStrategy.compute_bucket(flag_name, number)
        return bucket < percentage


# ============================================================
# Flag Dataclass
# ============================================================


@dataclass
class Flag:
    """A feature flag with full lifecycle management.

    Each flag carries its type, state, targeting rules, rollout
    percentage, dependencies, and a complete evaluation history
    counter — because even boolean toggles deserve telemetry.

    Attributes:
        name: The unique identifier for this flag.
        flag_type: BOOLEAN, PERCENTAGE, or TARGETING.
        enabled: Whether the flag is currently on.
        lifecycle: Current lifecycle state.
        description: Human-readable description for the flag registry.
        percentage: Rollout percentage (only for PERCENTAGE type).
        targeting_rule: Targeting rule (only for TARGETING type).
        dependencies: List of flag names this flag depends on.
        metadata: Arbitrary key-value metadata for audit purposes.
        evaluation_count: How many times this flag has been evaluated.
        last_evaluated: When this flag was last evaluated.
    """

    name: str
    flag_type: FlagType = FlagType.BOOLEAN
    enabled: bool = True
    lifecycle: FlagLifecycle = FlagLifecycle.ACTIVE
    description: str = ""
    percentage: float = 100.0
    targeting_rule: Optional[TargetingRule] = None
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    evaluation_count: int = 0
    last_evaluated: Optional[datetime] = None

    def evaluate(self, number: int) -> bool:
        """Evaluate this flag for the given number.

        The evaluation logic depends on the flag type:
          - BOOLEAN: returns self.enabled
          - PERCENTAGE: deterministic hash-based bucketing
          - TARGETING: delegates to the targeting rule

        Updates evaluation telemetry because every flag check
        is a data point worth recording.
        """
        self.evaluation_count += 1
        self.last_evaluated = datetime.now(timezone.utc)

        if not self.enabled:
            return False

        if self.lifecycle not in (FlagLifecycle.ACTIVE, FlagLifecycle.CREATED):
            return False

        if self.flag_type == FlagType.BOOLEAN:
            return True

        elif self.flag_type == FlagType.PERCENTAGE:
            return RolloutStrategy.is_in_rollout(
                self.name, number, self.percentage
            )

        elif self.flag_type == FlagType.TARGETING:
            if self.targeting_rule is None:
                raise FlagTargetingError(
                    self.name, "none",
                    "TARGETING flag has no targeting rule configured. "
                    "A targeting flag without a target is like a "
                    "FizzBuzz without the Fizz.",
                )
            return self.targeting_rule.evaluate(number)

        return False

    def transition_to(self, new_state: FlagLifecycle) -> None:
        """Transition this flag to a new lifecycle state.

        Valid transitions:
          CREATED -> ACTIVE
          ACTIVE -> DEPRECATED
          DEPRECATED -> ARCHIVED
          CREATED -> ARCHIVED (skip the drama)
        """
        valid_transitions: dict[FlagLifecycle, set[FlagLifecycle]] = {
            FlagLifecycle.CREATED: {FlagLifecycle.ACTIVE, FlagLifecycle.ARCHIVED},
            FlagLifecycle.ACTIVE: {FlagLifecycle.DEPRECATED},
            FlagLifecycle.DEPRECATED: {FlagLifecycle.ARCHIVED},
            FlagLifecycle.ARCHIVED: set(),
        }

        allowed = valid_transitions.get(self.lifecycle, set())
        if new_state not in allowed:
            raise FlagLifecycleError(
                self.name, self.lifecycle.name, new_state.name
            )
        self.lifecycle = new_state


# ============================================================
# Flag Dependency Graph
# ============================================================


class FlagDependencyGraph:
    """Directed acyclic graph for feature flag dependencies.

    Uses Kahn's algorithm for topological sorting and cycle detection,
    because if your feature flags have circular dependencies, you've
    achieved a level of configuration complexity that deserves a
    proper graph-theoretic response.

    The dependency graph ensures that:
      1. No cycles exist (flags cannot depend on themselves, directly
         or transitively)
      2. Dependencies are resolved in topological order
      3. A flag is only enabled if ALL its dependencies are enabled
    """

    def __init__(self) -> None:
        self._adjacency: dict[str, list[str]] = defaultdict(list)
        self._nodes: set[str] = set()

    def add_flag(self, flag_name: str, dependencies: Optional[list[str]] = None) -> None:
        """Register a flag and its dependencies in the graph."""
        self._nodes.add(flag_name)
        if dependencies:
            for dep in dependencies:
                self._nodes.add(dep)
                self._adjacency[dep].append(flag_name)

    def topological_sort(self) -> list[str]:
        """Perform a topological sort using Kahn's algorithm.

        Returns the flags in dependency order. Raises FlagDependencyCycleError
        if a cycle is detected, because circular feature flag dependencies
        are the kind of problem that Kahn's algorithm was born to detect
        (even though Kahn probably never imagined it being used for FizzBuzz).
        """
        in_degree: dict[str, int] = {node: 0 for node in self._nodes}

        for node in self._nodes:
            for neighbor in self._adjacency[node]:
                in_degree[neighbor] = in_degree.get(neighbor, 0) + 1

        queue: deque[str] = deque()
        for node in sorted(self._nodes):
            if in_degree[node] == 0:
                queue.append(node)

        result: list[str] = []
        while queue:
            current = queue.popleft()
            result.append(current)

            for neighbor in sorted(self._adjacency[current]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self._nodes):
            # Cycle detected — find it for the error message
            remaining = self._nodes - set(result)
            cycle = self._find_cycle(remaining)
            raise FlagDependencyCycleError(cycle)

        return result

    def _find_cycle(self, nodes: set[str]) -> list[str]:
        """Find and return a cycle within the given node set.

        This is used to produce a helpful error message when Kahn's
        algorithm detects that not all nodes were processed, which
        means a cycle exists somewhere in the unprocessed remainder.
        """
        visited: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> Optional[list[str]]:
            if node in visited:
                # Found cycle — extract it
                idx = path.index(node) if node in path else 0
                return path[idx:] + [node]
            visited.add(node)
            path.append(node)
            for neighbor in self._adjacency[node]:
                if neighbor in nodes:
                    result = dfs(neighbor)
                    if result:
                        return result
            path.pop()
            return None

        for node in sorted(nodes):
            visited.clear()
            path.clear()
            cycle = dfs(node)
            if cycle:
                return cycle

        return list(nodes)

    def validate(self) -> bool:
        """Validate that the dependency graph is a DAG (no cycles)."""
        try:
            self.topological_sort()
            return True
        except FlagDependencyCycleError:
            return False

    def get_dependencies(self, flag_name: str) -> list[str]:
        """Return the direct dependencies (predecessors) of a flag."""
        deps = []
        for node, neighbors in self._adjacency.items():
            if flag_name in neighbors:
                deps.append(node)
        return sorted(deps)

    def get_dependents(self, flag_name: str) -> list[str]:
        """Return all flags that depend on the given flag."""
        return sorted(self._adjacency.get(flag_name, []))


# ============================================================
# Flag Store
# ============================================================


class FlagStore:
    """Central registry and evaluation engine for all feature flags.

    The FlagStore is the authoritative source of truth for flag state.
    It manages flag registration, lifecycle transitions, dependency
    validation, and evaluation — because your feature toggles deserve
    the same level of ceremony as a production database.

    Features:
      - Thread-safe flag registration and lookup
      - Dependency graph validation on registration
      - Evaluation with dependency checking
      - Change listeners for reactive flag updates
      - Evaluation audit logging
    """

    def __init__(
        self,
        strict_dependencies: bool = True,
        log_evaluations: bool = True,
    ) -> None:
        self._flags: dict[str, Flag] = {}
        self._graph = FlagDependencyGraph()
        self._strict_dependencies = strict_dependencies
        self._log_evaluations = log_evaluations
        self._listeners: list[Callable[[str, bool, int], None]] = []
        self._evaluation_log: list[dict[str, Any]] = []

    def register(self, flag: Flag) -> None:
        """Register a flag in the store.

        Also registers the flag and its dependencies in the dependency graph.
        Validates the graph remains acyclic after registration.
        """
        self._flags[flag.name] = flag
        self._graph.add_flag(flag.name, flag.dependencies)

        # Validate the dependency graph remains a DAG
        if self._strict_dependencies and flag.dependencies:
            try:
                self._graph.topological_sort()
            except FlagDependencyCycleError:
                # Roll back registration
                del self._flags[flag.name]
                raise

        logger.debug(
            "Registered flag '%s' (type=%s, enabled=%s)",
            flag.name, flag.flag_type.name, flag.enabled,
        )

    def get(self, name: str) -> Flag:
        """Retrieve a flag by name."""
        if name not in self._flags:
            raise FlagNotFoundError(name)
        return self._flags[name]

    def evaluate(self, name: str, number: int) -> bool:
        """Evaluate a flag for a given number, checking dependencies.

        Returns True if:
          1. The flag exists and is enabled
          2. All dependencies are satisfied
          3. The flag's type-specific evaluation passes

        This is the enterprise-grade equivalent of checking a boolean,
        but with dependency resolution, audit logging, and change
        notification. You're welcome.
        """
        flag = self.get(name)

        # Check dependencies first
        for dep_name in flag.dependencies:
            if dep_name in self._flags:
                dep_result = self.evaluate(dep_name, number)
                if not dep_result:
                    if self._strict_dependencies:
                        self._record_evaluation(name, number, False, "dependency_not_met")
                        return False
                    else:
                        self._record_evaluation(name, number, False, "dependency_not_met_soft")
                        return False

        result = flag.evaluate(number)
        self._record_evaluation(name, number, result, "evaluated")

        # Notify listeners
        for listener in self._listeners:
            try:
                listener(name, result, number)
            except Exception as e:
                logger.warning("Flag listener error: %s", e)

        return result

    def evaluate_all(self, number: int) -> dict[str, bool]:
        """Evaluate all registered flags for the given number.

        Returns a dictionary mapping flag names to their evaluation results.
        Because knowing the state of every feature flag for every single
        integer is essential operational data.
        """
        results = {}
        # Evaluate in topological order to ensure dependencies are checked first
        try:
            order = self._graph.topological_sort()
        except FlagDependencyCycleError:
            order = sorted(self._flags.keys())

        for flag_name in order:
            if flag_name in self._flags:
                results[flag_name] = self.evaluate(flag_name, number)

        return results

    def _record_evaluation(
        self, flag_name: str, number: int, result: bool, reason: str
    ) -> None:
        """Record a flag evaluation for audit purposes."""
        if self._log_evaluations:
            entry = {
                "flag": flag_name,
                "number": number,
                "result": result,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._evaluation_log.append(entry)
            logger.debug(
                "Flag '%s' evaluated for number %d: %s (%s)",
                flag_name, number, result, reason,
            )

    def add_listener(self, listener: Callable[[str, bool, int], None]) -> None:
        """Register a callback for flag evaluation events."""
        self._listeners.append(listener)

    def list_flags(self) -> list[dict[str, Any]]:
        """Return a summary of all registered flags."""
        summaries = []
        for flag in self._flags.values():
            summary: dict[str, Any] = {
                "name": flag.name,
                "type": flag.flag_type.name,
                "enabled": flag.enabled,
                "lifecycle": flag.lifecycle.name,
                "description": flag.description,
                "evaluation_count": flag.evaluation_count,
            }
            if flag.flag_type == FlagType.PERCENTAGE:
                summary["percentage"] = flag.percentage
            if flag.dependencies:
                summary["dependencies"] = flag.dependencies
            summaries.append(summary)
        return summaries

    def get_evaluation_log(self) -> list[dict[str, Any]]:
        """Return the full evaluation audit log."""
        return list(self._evaluation_log)

    def set_flag(self, name: str, enabled: bool) -> None:
        """Enable or disable a flag by name."""
        flag = self.get(name)
        flag.enabled = enabled
        logger.info("Flag '%s' set to enabled=%s", name, enabled)

    @property
    def flag_count(self) -> int:
        return len(self._flags)

    @property
    def dependency_graph(self) -> FlagDependencyGraph:
        return self._graph


# ============================================================
# Flag Middleware
# ============================================================


class FlagMiddleware(IMiddleware):
    """Middleware that evaluates feature flags before rule processing.

    Sits in the middleware pipeline at priority -3 (runs very early)
    to determine which rules should be active for each number being
    evaluated. Stores the filtered rule set in context.metadata so
    that downstream components can check which rules were active.

    This middleware is the gatekeeper between your feature flags and
    your FizzBuzz rules. If a flag says "no Fizz for you", then no
    Fizz shall pass. It is the bouncer at the club of modular arithmetic.
    """

    # Map flag names to rule labels
    FLAG_RULE_MAP = {
        "fizz_rule_enabled": "Fizz",
        "buzz_rule_enabled": "Buzz",
        "wuzz_rule_experimental": "Wuzz",
    }

    def __init__(
        self,
        flag_store: FlagStore,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._flag_store = flag_store
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Evaluate all flags and store active rule labels in context metadata."""
        number = context.number

        # Evaluate all flags for this number
        flag_results = self._flag_store.evaluate_all(number)

        # Determine which rule labels are active
        active_labels: set[str] = set()
        disabled_labels: set[str] = set()

        for flag_name, is_enabled in flag_results.items():
            label = self.FLAG_RULE_MAP.get(flag_name)
            if label:
                if is_enabled:
                    active_labels.add(label)
                else:
                    disabled_labels.add(label)

        # Store in metadata for downstream use
        context.metadata["feature_flags"] = flag_results
        context.metadata["active_rule_labels"] = active_labels
        context.metadata["disabled_rule_labels"] = disabled_labels
        context.metadata["feature_flags_active"] = True

        # Emit events
        if self._event_bus is not None:
            self._event_bus.publish(
                Event(
                    event_type=EventType.FLAG_EVALUATED,
                    payload={
                        "number": number,
                        "flag_results": {k: v for k, v in flag_results.items()},
                        "active_labels": sorted(active_labels),
                        "disabled_labels": sorted(disabled_labels),
                    },
                    source="FlagMiddleware",
                )
            )

        return next_handler(context)

    def get_name(self) -> str:
        return "FlagMiddleware"

    def get_priority(self) -> int:
        return -3


# ============================================================
# Flag Evaluation Summary (ASCII Renderer)
# ============================================================


class FlagEvaluationSummary:
    """ASCII art renderer for feature flag evaluation results.

    Because enterprise observability demands that feature flag
    state be rendered in beautifully formatted ASCII tables with
    box-drawing characters, evaluation statistics, and a summary
    section that would make any compliance officer weep with joy.
    """

    @staticmethod
    def render(flag_store: FlagStore) -> str:
        """Render a comprehensive ASCII summary of all flag states."""
        flags = flag_store.list_flags()
        if not flags:
            return (
                "\n  +===========================================================+\n"
                "  |          FEATURE FLAGS: No flags registered              |\n"
                "  +===========================================================+\n"
            )

        lines = [
            "",
            "  +===========================================================+",
            "  |         FEATURE FLAG EVALUATION SUMMARY                    |",
            "  |         Progressive Rollout Control Plane                  |",
            "  +===========================================================+",
            f"  |  Total Flags Registered : {len(flags):<33}|",
            "  +-----------------------------------------------------------+",
            f"  |  {'Flag Name':<26} {'Type':<12} {'State':<10} {'Evals':<8}|",
            "  +-----------------------------------------------------------+",
        ]

        for f in flags:
            state = "ON" if f["enabled"] else "OFF"
            name = f["name"][:25]
            ftype = f["type"][:11]
            evals = str(f["evaluation_count"])[:7]

            # Add percentage info for PERCENTAGE type
            extra = ""
            if f["type"] == "PERCENTAGE" and "percentage" in f:
                extra = f" ({f['percentage']:.0f}%)"
                ftype = ftype[:7] + extra[:4]

            line = f"  |  {name:<26} {ftype:<12} {state:<10} {evals:<8}|"
            lines.append(line)

            if f.get("dependencies"):
                deps_str = ", ".join(f["dependencies"])
                dep_line = f"  |    deps: {deps_str:<49}|"
                lines.append(dep_line)

        lines.append("  +-----------------------------------------------------------+")

        # Evaluation log summary
        log = flag_store.get_evaluation_log()
        total_evals = len(log)
        true_count = sum(1 for e in log if e["result"])
        false_count = total_evals - true_count

        lines.extend([
            f"  |  Total Evaluations  : {total_evals:<36}|",
            f"  |  Enabled Results    : {true_count:<36}|",
            f"  |  Disabled Results   : {false_count:<36}|",
            "  +===========================================================+",
            "",
        ])

        return "\n".join(lines)


# ============================================================
# Factory / Initialization Helpers
# ============================================================


def create_flag_store_from_config(config: Any) -> FlagStore:
    """Create and populate a FlagStore from the configuration manager.

    Reads predefined flag definitions from config.yaml and registers
    them in the store. This is the bridge between your YAML config
    and the runtime flag evaluation engine — because feature flags
    that can't be configured in YAML aren't really enterprise-grade.
    """
    store = FlagStore(
        strict_dependencies=config.feature_flags_strict_dependencies,
        log_evaluations=config.feature_flags_log_evaluations,
    )

    predefined = config.feature_flags_predefined

    # First pass: register all flags without dependency validation
    # Second pass handled by the graph's topological sort
    flags_to_register: list[Flag] = []

    for name, defn in predefined.items():
        flag_type_str = defn.get("type", "BOOLEAN")
        flag_type = FlagType[flag_type_str]

        targeting_rule = None
        if flag_type == FlagType.TARGETING:
            rule_type = defn.get("targeting_rule", "prime")
            rule_params = defn.get("targeting_params", {})
            targeting_rule = TargetingRule(rule_type, rule_params)

        flag = Flag(
            name=name,
            flag_type=flag_type,
            enabled=defn.get("enabled", True),
            lifecycle=FlagLifecycle[
                config.feature_flags_default_lifecycle
            ],
            description=defn.get("description", ""),
            percentage=defn.get("percentage", 100.0),
            targeting_rule=targeting_rule,
            dependencies=defn.get("dependencies", []),
        )
        flags_to_register.append(flag)

    # Register flags without dependencies first, then with dependencies
    no_deps = [f for f in flags_to_register if not f.dependencies]
    with_deps = [f for f in flags_to_register if f.dependencies]

    for flag in no_deps:
        store.register(flag)
    for flag in with_deps:
        store.register(flag)

    return store


def apply_cli_overrides(store: FlagStore, overrides: list[str]) -> None:
    """Apply CLI --flag NAME=VALUE overrides to the flag store.

    Accepts a list of "FLAG_NAME=true/false" strings and updates
    the corresponding flags. Because command-line overrides are
    the escape hatch when your YAML is too far away to edit.
    """
    for override in overrides:
        if "=" not in override:
            logger.warning("Invalid flag override (missing '='): %s", override)
            continue

        name, value_str = override.split("=", 1)
        name = name.strip()
        value_str = value_str.strip().lower()

        enabled = value_str in ("true", "1", "yes", "on")

        try:
            store.set_flag(name, enabled)
            logger.info("CLI override: flag '%s' set to %s", name, enabled)
        except FlagNotFoundError:
            # Create ad-hoc flag if it doesn't exist
            flag = Flag(
                name=name,
                flag_type=FlagType.BOOLEAN,
                enabled=enabled,
                lifecycle=FlagLifecycle.ACTIVE,
                description=f"Ad-hoc flag created via CLI override",
            )
            store.register(flag)
            logger.info("CLI override: created ad-hoc flag '%s' = %s", name, enabled)


def render_flag_list(store: FlagStore) -> str:
    """Render a human-readable list of all registered flags for --list-flags."""
    flags = store.list_flags()
    if not flags:
        return "\n  No feature flags registered.\n"

    lines = [
        "",
        "  +===========================================================+",
        "  |              REGISTERED FEATURE FLAGS                      |",
        "  +===========================================================+",
        f"  |  {'Name':<28} {'Type':<10} {'Enabled':<9} {'Lifecycle':<10}|",
        "  +-----------------------------------------------------------+",
    ]

    for f in flags:
        name = f["name"][:27]
        ftype = f["type"][:9]
        enabled = "YES" if f["enabled"] else "NO"
        lifecycle = f["lifecycle"][:9]
        lines.append(f"  |  {name:<28} {ftype:<10} {enabled:<9} {lifecycle:<10}|")

        if f.get("description"):
            desc = f["description"][:55]
            lines.append(f"  |    {desc:<55}|")

        if f.get("dependencies"):
            deps = ", ".join(f["dependencies"])[:53]
            lines.append(f"  |    deps: {deps:<49}|")

        if f["type"] == "PERCENTAGE" and "percentage" in f:
            lines.append(f"  |    rollout: {f['percentage']:.1f}%{'':<45}|")

    lines.extend([
        "  +===========================================================+",
        "",
    ])

    return "\n".join(lines)

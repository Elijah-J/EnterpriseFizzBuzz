"""── OS Kernel properties ────────────────────────────────"""

from __future__ import annotations

from typing import Any


class SelfModifyingConfigMixin:
    """Configuration properties for the self modifying subsystem."""

    @property
    def self_modifying_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("enabled", False)

    @property
    def self_modifying_mutation_rate(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("mutation_rate", 0.05)

    @property
    def self_modifying_max_ast_depth(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("max_ast_depth", 10)

    @property
    def self_modifying_correctness_floor(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("correctness_floor", 0.95)

    @property
    def self_modifying_max_mutations_per_session(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("max_mutations_per_session", 100)

    @property
    def self_modifying_kill_switch(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("kill_switch", True)

    @property
    def self_modifying_fitness_correctness_weight(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("fitness_weights", {}).get("correctness", 0.70)

    @property
    def self_modifying_fitness_latency_weight(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("fitness_weights", {}).get("latency", 0.20)

    @property
    def self_modifying_fitness_compactness_weight(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("fitness_weights", {}).get("compactness", 0.10)

    @property
    def self_modifying_enabled_operators(self) -> list[str]:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("enabled_operators", [
            "DivisorShift", "LabelSwap", "BranchInvert", "InsertShortCircuit",
            "DeadCodePrune", "SubtreeSwap", "DuplicateSubtree", "NegateCondition",
            "ConstantFold", "InsertRedundantCheck", "ShuffleChildren", "WrapInConditional",
        ])

    @property
    def self_modifying_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("dashboard", {}).get("width", 60)

    @property
    def self_modifying_dashboard_show_ast(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("dashboard", {}).get("show_ast", True)

    @property
    def self_modifying_dashboard_show_history(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("dashboard", {}).get("show_history", True)

    @property
    def self_modifying_dashboard_show_fitness(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("self_modifying", {}).get("dashboard", {}).get("show_fitness", True)

    # ── OS Kernel properties ────────────────────────────────


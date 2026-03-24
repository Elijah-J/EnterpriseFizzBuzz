"""FizzLang DSL properties"""

from __future__ import annotations

from typing import Any


class FizzlangConfigMixin:
    """Configuration properties for the fizzlang subsystem."""

    # ------------------------------------------------------------------
    # FizzLang DSL properties
    # ------------------------------------------------------------------

    @property
    def fizzlang_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("enabled", False)

    @property
    def fizzlang_max_program_length(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("max_program_length", 10000)

    @property
    def fizzlang_max_rules(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("max_rules", 50)

    @property
    def fizzlang_max_let_bindings(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("max_let_bindings", 100)

    @property
    def fizzlang_strict_type_checking(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("strict_type_checking", True)

    @property
    def fizzlang_stdlib_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("stdlib_enabled", True)

    @property
    def fizzlang_repl_prompt(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("repl", {}).get("prompt", "fizz> ")

    @property
    def fizzlang_repl_history_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("repl", {}).get("history_size", 100)

    @property
    def fizzlang_repl_show_tokens(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("repl", {}).get("show_tokens", False)

    @property
    def fizzlang_repl_show_ast(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("repl", {}).get("show_ast", False)

    @property
    def fizzlang_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("dashboard", {}).get("width", 60)

    @property
    def fizzlang_dashboard_show_source_stats(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("dashboard", {}).get("show_source_stats", True)

    @property
    def fizzlang_dashboard_show_complexity_index(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlang", {}).get("dashboard", {}).get("show_complexity_index", True)


"""
Enterprise FizzBuzz Platform - Internationalization (i18n) Module

Provides a comprehensive, enterprise-grade localization subsystem for the
FizzBuzz evaluation pipeline. Because saying "Fizz" in only one language
is a clear violation of ISO 639 best practices, and our stakeholders
demand multi-lingual modulo arithmetic.

Features:
    - Proprietary .fizztranslation file format (because YAML was too mainstream)
    - Locale fallback chains (because one language is never enough)
    - Pluralization engine (because "1 Fizzes" is a crime against grammar)
    - Singleton-based locale management (because global state is an enterprise pattern)
    - Variable interpolation with ${var} syntax (because printf was too simple)
"""

from __future__ import annotations

import logging
import re
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional

from config import _SingletonMeta
from exceptions import (
    FizzTranslationParseError,
    LocaleChainExhaustedError,
    LocaleError,
    LocaleNotFoundError,
    PluralizationError,
    TranslationKeyError,
)

logger = logging.getLogger(__name__)

# Default locale directory, relative to this file
_DEFAULT_LOCALE_DIR = Path(__file__).parent / "locales"


# ============================================================
# Parser State Machine
# ============================================================


class _ParserState(Enum):
    """Internal states for the .fizztranslation file parser.

    A proper state machine, because parsing a text file without one
    would be uncivilized.
    """

    METADATA = auto()
    SECTION = auto()
    HEREDOC = auto()


# ============================================================
# TranslationCatalog
# ============================================================


class TranslationCatalog:
    """Stores all translations for a single locale.

    Acts as a dictionary-of-dictionaries, keyed by section.key,
    with support for plural forms and variable interpolation.
    Think of it as a HashMap, but with cultural sensitivity.

    Attributes:
        _entries: Flat key-value store keyed by "section.key".
        _plural_entries: Nested dict keyed by "section.key" -> {form -> value}.
        _metadata: Locale directives from @-prefixed lines.
    """

    def __init__(self) -> None:
        self._entries: dict[str, str] = {}
        self._plural_entries: dict[str, dict[str, str]] = {}
        self._metadata: dict[str, str] = {}

    @property
    def locale(self) -> str:
        """The locale code for this catalog (e.g. 'en', 'fr', 'tlh')."""
        return self._metadata.get("locale", "unknown")

    @property
    def name(self) -> str:
        """Human-readable locale name."""
        return self._metadata.get("name", "Unknown")

    @property
    def fallback(self) -> Optional[str]:
        """The fallback locale code, if any."""
        fb = self._metadata.get("fallback")
        if fb and fb.lower() == "none":
            return None
        return fb

    @property
    def plural_rule(self) -> str:
        """The plural rule expression for this locale."""
        return self._metadata.get("plural_rule", "n != 1")

    @property
    def metadata(self) -> dict[str, str]:
        """All metadata directives."""
        return dict(self._metadata)

    def set_metadata(self, key: str, value: str) -> None:
        """Set a metadata directive."""
        self._metadata[key] = value

    def set_entry(self, section: str, key: str, value: str) -> None:
        """Set a translation entry."""
        full_key = f"{section}.{key}"
        self._entries[full_key] = value

    def set_plural_entry(
        self, section: str, key: str, form: str, value: str
    ) -> None:
        """Set a plural form entry."""
        full_key = f"{section}.{key}"
        if full_key not in self._plural_entries:
            self._plural_entries[full_key] = {}
        self._plural_entries[full_key][form] = value

    def get(self, key: str, **kwargs: Any) -> Optional[str]:
        """Look up a translation key and apply variable interpolation.

        Args:
            key: The fully-qualified key (e.g. "messages.evaluating").
            **kwargs: Variables to interpolate (e.g. start=1, end=100).

        Returns:
            The translated, interpolated string, or None if not found.
        """
        value = self._entries.get(key)
        if value is None:
            return None
        return self._interpolate(value, kwargs)

    def get_plural(
        self, key: str, count: int, form: str, **kwargs: Any
    ) -> Optional[str]:
        """Look up a plural form and apply variable interpolation.

        Args:
            key: The fully-qualified key (e.g. "plurals.Fizz.plural").
            count: The count for interpolation.
            form: The plural form (e.g. "one", "other").
            **kwargs: Additional interpolation variables.

        Returns:
            The pluralized, interpolated string, or None if not found.
        """
        forms = self._plural_entries.get(key)
        if forms is None:
            return None
        value = forms.get(form)
        if value is None:
            return None
        kwargs["count"] = count
        return self._interpolate(value, kwargs)

    def has_key(self, key: str) -> bool:
        """Check if a translation key exists."""
        return key in self._entries

    def get_all_keys(self) -> list[str]:
        """Return all translation keys."""
        return list(self._entries.keys())

    @staticmethod
    def _interpolate(template: str, variables: dict[str, Any]) -> str:
        """Replace ${var} placeholders with provided values.

        This is our proprietary template engine. It does exactly one thing
        and does it adequately. No Turing-completeness here.
        """
        result = template
        for var_name, var_value in variables.items():
            result = result.replace(f"${{{var_name}}}", str(var_value))
        return result


# ============================================================
# FizzTranslationParser
# ============================================================


class FizzTranslationParser:
    """Parses the proprietary .fizztranslation file format.

    The .fizztranslation format is a purpose-built configuration language
    designed specifically for Enterprise FizzBuzz localization needs.
    It supports metadata directives, sections, key-value pairs, heredocs,
    and comments -- everything you need to say "Fizz" in Klingon.

    File format specification:
        - Comments: Lines starting with ';;' are ignored.
        - Metadata: Lines starting with '@key = value' (before any section).
        - Sections: '[section_name]' headers.
        - Key-value: 'key = value' lines within a section.
        - Heredoc: When a value starts with '<<WORD', reads until WORD appears
          on a line by itself.
        - Blank lines: Ignored everywhere.

    Raises:
        FizzTranslationParseError: On any syntax violation.
    """

    def parse(self, file_path: str) -> TranslationCatalog:
        """Parse a .fizztranslation file and return a TranslationCatalog.

        Args:
            file_path: Path to the .fizztranslation file.

        Returns:
            A fully-populated TranslationCatalog.

        Raises:
            FizzTranslationParseError: If the file contains syntax errors.
        """
        catalog = TranslationCatalog()
        path = Path(file_path)

        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        state = _ParserState.METADATA
        current_section: Optional[str] = None
        heredoc_terminator: Optional[str] = None
        heredoc_lines: list[str] = []
        heredoc_key: Optional[str] = None
        heredoc_start_line: int = 0

        for line_number, raw_line in enumerate(lines, start=1):
            line = raw_line.rstrip("\n").rstrip("\r")

            # --- HEREDOC state: accumulate lines until terminator ---
            if state == _ParserState.HEREDOC:
                if line.strip() == heredoc_terminator:
                    # End of heredoc block
                    value = "\n".join(heredoc_lines)
                    if current_section and heredoc_key:
                        catalog.set_entry(current_section, heredoc_key, value)
                    state = _ParserState.SECTION
                    heredoc_terminator = None
                    heredoc_lines = []
                    heredoc_key = None
                else:
                    heredoc_lines.append(line)
                continue

            # --- Skip blank lines and comments ---
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(";;") or stripped.startswith("#"):
                continue

            # --- Legacy format: @@key: value metadata (v1 compat) ---
            if stripped.startswith("@@") and ":" in stripped:
                content = stripped[2:].strip()
                key_part, _, value_part = content.partition(":")
                catalog.set_metadata(key_part.strip(), value_part.strip())
                continue

            # --- Legacy format: >> key = value entries (v1 compat) ---
            # Maps old-style dotted keys to the new section.key format:
            #   fizz.label -> labels.Fizz
            #   fizz.plural -> plurals with pipe-split
            #   summary.title -> summary.title
            #   status.evaluating -> messages.evaluating
            #   banner.subtitle -> banner.subtitle
            if stripped.startswith(">>") and "=" in stripped:
                content = stripped[2:].strip()
                key_part, _, value_part = content.partition("=")
                key = key_part.strip()
                value = value_part.strip()

                if "." in key:
                    prefix, suffix = key.split(".", 1)

                    # Label entries: fizz.label -> labels.Fizz
                    if suffix == "label":
                        label_map = {"fizz": "Fizz", "buzz": "Buzz", "fizzbuzz": "FizzBuzz"}
                        label_key = label_map.get(prefix, prefix.capitalize())
                        catalog.set_entry("labels", label_key, value)

                    # Plural entries: fizz.plural = singular | plural
                    elif suffix == "plural" and "|" in value:
                        forms = [f.strip() for f in value.split("|")]
                        label_map = {"fizz": "Fizz", "buzz": "Buzz", "fizzbuzz": "FizzBuzz"}
                        base = label_map.get(prefix, prefix.capitalize())
                        if len(forms) >= 2:
                            catalog.set_plural_entry(
                                "plurals", f"{base}.plural", "one", forms[0]
                            )
                            catalog.set_plural_entry(
                                "plurals", f"{base}.plural", "other", forms[1]
                            )

                    # Status entries: status.evaluating -> messages.evaluating
                    elif prefix == "status":
                        catalog.set_entry("messages", suffix, value)

                    # Everything else: section.key as-is
                    else:
                        catalog.set_entry(prefix, suffix, value)
                else:
                    catalog.set_entry("misc", key, value)
                continue

            # --- Metadata lines (@key = value) ---
            if stripped.startswith("@") and "=" in stripped:
                key_part, _, value_part = stripped[1:].partition("=")
                catalog.set_metadata(key_part.strip(), value_part.strip())
                if state == _ParserState.METADATA:
                    continue
                continue

            # --- Section headers ---
            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped[1:-1].strip()
                state = _ParserState.SECTION
                continue

            # --- Key-value pairs (must be in a section) ---
            if state == _ParserState.SECTION and current_section and "=" in stripped:
                key_part, _, value_part = stripped.partition("=")
                key = key_part.strip()
                value = value_part.strip()

                # Check for heredoc start
                if value.startswith("<<"):
                    heredoc_terminator = value[2:].strip()
                    heredoc_key = key
                    heredoc_lines = []
                    heredoc_start_line = line_number
                    state = _ParserState.HEREDOC
                    continue

                # Check if this is a plural entry (key contains ".plural.")
                # Format: Fizz.plural.one = Fizz
                plural_match = re.match(
                    r"^(.+)\.plural\.(one|other|zero|few|many|two)$", key
                )
                if plural_match and current_section == "plurals":
                    base_key = plural_match.group(1)
                    form = plural_match.group(2)
                    catalog.set_plural_entry(
                        current_section, f"{base_key}.plural", form, value
                    )
                else:
                    catalog.set_entry(current_section, key, value)
                continue

            # --- If we get here in METADATA state with a non-metadata line,
            # it's probably a key-value without a section ---
            if state == _ParserState.METADATA and "=" in stripped:
                # Treat as metadata-like (graceful degradation)
                logger.warning(
                    "Key-value pair '%s' found outside any section at line %d in %s",
                    stripped,
                    line_number,
                    file_path,
                )
                continue

            # --- Unrecognized line ---
            # Be lenient: just warn, don't crash
            logger.warning(
                "Ignoring unrecognized line %d in %s: %r",
                line_number,
                file_path,
                stripped,
            )

        # Check for unterminated heredoc
        if state == _ParserState.HEREDOC:
            raise FizzTranslationParseError(
                file_path,
                heredoc_start_line,
                f"Unterminated heredoc (expected '{heredoc_terminator}')",
            )

        logger.debug(
            "Parsed locale '%s' from %s: %d entries, %d plural groups",
            catalog.locale,
            file_path,
            len(catalog._entries),
            len(catalog._plural_entries),
        )

        return catalog

    def parse_string(self, content: str, source: str = "<string>") -> TranslationCatalog:
        """Parse .fizztranslation content from a string.

        Useful for testing without touching the filesystem, because
        unit tests should not require actual Klingon locale files.

        Args:
            content: The file content as a string.
            source: A label for error messages.

        Returns:
            A fully-populated TranslationCatalog.
        """
        import tempfile
        import os

        # Write to a temp file and parse it, because we already wrote
        # a perfectly good file parser and reuse is an enterprise virtue
        fd, tmp_path = tempfile.mkstemp(suffix=".fizztranslation")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            return self.parse(tmp_path)
        finally:
            os.unlink(tmp_path)


# ============================================================
# PluralizationEngine
# ============================================================


class PluralizationEngine:
    """Determines the correct plural form for a given count and locale.

    Implements a subset of CLDR plural rules, because the full CLDR
    specification has more edge cases than the entire FizzBuzz problem space.

    Supported rules:
        - English/German/Klingon: n != 1 -> "one" vs "other"
        - French: n > 1 -> "one" vs "other" (0 is singular in French)
        - Japanese: always "other" (no grammatical plural)
    """

    # Built-in plural rule expressions
    _BUILTIN_RULES: dict[str, str] = {
        "en": "n != 1",
        "de": "n != 1",
        "tlh": "n != 1",
        "fr": "n > 1",
        "ja": "0",  # Always "other"
    }

    # Named rule aliases for backwards compatibility with legacy format
    _NAMED_RULES: dict[str, str] = {
        "english": "n != 1",
        "german": "n != 1",
        "french": "n > 1",
        "japanese": "0",
        "klingon": "n != 1",
    }

    def get_form(self, locale: str, count: int, rule: Optional[str] = None) -> str:
        """Determine the plural form for the given count.

        Args:
            locale: The locale code.
            count: The number to pluralize for.
            rule: Optional rule expression override.

        Returns:
            The plural form string: "one", "other", "zero", etc.

        Raises:
            PluralizationError: If the rule cannot be evaluated.
        """
        rule_expr = rule or self._BUILTIN_RULES.get(locale, "n != 1")

        # Resolve named rules (legacy format compatibility)
        if rule_expr in self._NAMED_RULES:
            rule_expr = self._NAMED_RULES[rule_expr]

        try:
            return self._evaluate_rule(rule_expr, count)
        except Exception as e:
            raise PluralizationError(locale, count, rule_expr) from e

    def _evaluate_rule(self, rule: str, count: int) -> str:
        """Evaluate a plural rule expression.

        The rule is a simple expression where 'n' represents the count.
        If the expression evaluates to True (or a truthy value), the
        form is "other"; otherwise it's "one".

        Special case: rule "0" always returns "other" (no grammatical plural).
        """
        # Special case: always "other" (e.g., Japanese)
        if rule.strip() == "0":
            return "other"

        # Evaluate the rule with n bound to count
        # We use a restricted eval because we trust our own locale files
        # (and because enterprise software never has security vulnerabilities)
        result = eval(rule, {"__builtins__": {}}, {"n": count})  # noqa: S307

        if result:
            return "other"
        else:
            return "one"


# ============================================================
# LocaleResolver
# ============================================================


class LocaleResolver:
    """Walks the locale fallback chain to resolve translation keys.

    When a key is not found in the requested locale, the resolver
    walks up the fallback chain (e.g., fr -> en) until it finds a
    translation or runs out of locales to check.

    This is essentially a linked list traversal, but we call it a
    "fallback chain" because that sounds more enterprise-y.
    """

    def build_chain(
        self,
        locale: str,
        catalogs: dict[str, TranslationCatalog],
        global_fallback: str = "en",
    ) -> list[str]:
        """Build the ordered fallback chain for a locale.

        Args:
            locale: The starting locale.
            catalogs: All loaded catalogs.
            global_fallback: The ultimate fallback locale.

        Returns:
            An ordered list of locale codes to try.
        """
        chain: list[str] = []
        visited: set[str] = set()
        current: Optional[str] = locale

        while current and current not in visited:
            if current in catalogs:
                chain.append(current)
            visited.add(current)
            catalog = catalogs.get(current)
            current = catalog.fallback if catalog else None

        # Add global fallback if not already in chain
        if global_fallback not in chain and global_fallback in catalogs:
            chain.append(global_fallback)

        return chain

    def resolve(
        self,
        locale: str,
        key: str,
        catalogs: dict[str, TranslationCatalog],
        global_fallback: str = "en",
        **kwargs: Any,
    ) -> Optional[str]:
        """Resolve a translation key by walking the fallback chain.

        Args:
            locale: The requested locale.
            key: The translation key (e.g., "messages.evaluating").
            catalogs: All loaded catalogs.
            global_fallback: The ultimate fallback locale.
            **kwargs: Variables for interpolation.

        Returns:
            The resolved translation, or None if not found anywhere.
        """
        chain = self.build_chain(locale, catalogs, global_fallback)

        for chain_locale in chain:
            catalog = catalogs.get(chain_locale)
            if catalog:
                result = catalog.get(key, **kwargs)
                if result is not None:
                    return result

        return None


# ============================================================
# LocaleManager (Singleton)
# ============================================================


class LocaleManager(metaclass=_SingletonMeta):
    """Singleton orchestrator for the entire i18n subsystem.

    Manages locale loading, switching, translation lookups, and
    pluralization -- all from one convenient global instance, because
    dependency injection is so last decade.

    Usage:
        mgr = LocaleManager()
        mgr.load_all("./locales")
        mgr.set_locale("fr")
        print(mgr.t("messages.evaluating", start=1, end=100))
        # -> "Evaluation de FizzBuzz pour la plage [1, 100]..."
    """

    def __init__(self) -> None:
        self._catalogs: dict[str, TranslationCatalog] = {}
        self._active_locale: str = "en"
        self._global_fallback: str = "en"
        self._parser = FizzTranslationParser()
        self._pluralization = PluralizationEngine()
        self._resolver = LocaleResolver()
        self._loaded = False
        self._strict_mode = False

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance. Essential for testing.

        Without this, tests would share locale state, and a French
        test would accidentally affect a Klingon test, which would
        be a diplomatic incident.
        """
        _SingletonMeta.reset()

    @property
    def active_locale(self) -> str:
        """The currently active locale code."""
        return self._active_locale

    @property
    def is_loaded(self) -> bool:
        """Whether locales have been loaded."""
        return self._loaded

    def load_all(self, directory: str) -> None:
        """Scan a directory for .fizztranslation files and parse them all.

        Args:
            directory: Path to the locales directory.

        Raises:
            LocaleNotFoundError: If the directory contains no locale files.
        """
        locale_dir = Path(directory)
        if not locale_dir.exists():
            logger.warning("Locale directory '%s' does not exist", directory)
            self._loaded = True
            return

        files = list(locale_dir.glob("*.fizztranslation"))
        if not files:
            logger.warning("No .fizztranslation files found in '%s'", directory)
            self._loaded = True
            return

        for file_path in files:
            try:
                catalog = self._parser.parse(str(file_path))
                locale_code = catalog.locale
                self._catalogs[locale_code] = catalog
                logger.info(
                    "Loaded locale '%s' (%s) from %s",
                    locale_code,
                    catalog.name,
                    file_path,
                )
            except FizzTranslationParseError:
                logger.error(
                    "Failed to parse locale file: %s", file_path, exc_info=True
                )
                raise

        self._loaded = True
        logger.info(
            "Loaded %d locale(s): %s",
            len(self._catalogs),
            ", ".join(sorted(self._catalogs.keys())),
        )

    def set_locale(self, locale: str) -> None:
        """Set the active locale.

        Args:
            locale: The locale code to activate.

        Raises:
            LocaleNotFoundError: If the locale has not been loaded.
        """
        if locale not in self._catalogs:
            raise LocaleNotFoundError(
                locale,
                searched_paths=list(self._catalogs.keys()),
            )
        self._active_locale = locale
        logger.info("Active locale set to '%s'", locale)

    def set_fallback(self, fallback: str) -> None:
        """Set the global fallback locale."""
        self._global_fallback = fallback

    def set_strict_mode(self, strict: bool) -> None:
        """Enable or disable strict mode.

        In strict mode, missing translations raise errors instead of
        returning the key as a fallback value.
        """
        self._strict_mode = strict

    def t(self, key: str, **kwargs: Any) -> str:
        """Translate a key using the active locale.

        The crown jewel of the i18n subsystem. Takes a dotted key
        and returns a fully interpolated translation string, falling
        back through the locale chain as needed.

        Args:
            key: The translation key (e.g., "messages.evaluating").
            **kwargs: Variables for interpolation.

        Returns:
            The translated string, or the key itself if not found.
        """
        result = self._resolver.resolve(
            self._active_locale,
            key,
            self._catalogs,
            self._global_fallback,
            **kwargs,
        )

        if result is not None:
            return result

        if self._strict_mode:
            chain = self._resolver.build_chain(
                self._active_locale, self._catalogs, self._global_fallback
            )
            raise TranslationKeyError(key, self._active_locale, chain)

        # Graceful degradation: return the key itself
        logger.debug(
            "Translation key '%s' not found for locale '%s', returning key",
            key,
            self._active_locale,
        )
        return key

    def tp(self, key: str, count: int, **kwargs: Any) -> str:
        """Translate a key with pluralization.

        Like t(), but takes a count and selects the appropriate plural form.
        Because "1 FizzBuzzes" is grammatically unacceptable in every language.

        Args:
            key: The base key (e.g., "plurals.Fizz.plural").
            count: The number to pluralize for.
            **kwargs: Additional interpolation variables.

        Returns:
            The pluralized, translated string.
        """
        chain = self._resolver.build_chain(
            self._active_locale, self._catalogs, self._global_fallback
        )

        for chain_locale in chain:
            catalog = self._catalogs.get(chain_locale)
            if catalog:
                # Determine plural form using the catalog's rule
                form = self._pluralization.get_form(
                    chain_locale, count, catalog.plural_rule
                )
                result = catalog.get_plural(key, count, form, **kwargs)
                if result is not None:
                    return result

        if self._strict_mode:
            raise TranslationKeyError(key, self._active_locale, chain)

        return key

    def get_label(self, label: str) -> str:
        """Translate a FizzBuzz label (Fizz, Buzz, FizzBuzz).

        Convenience method for the most common translation operation:
        converting English labels to the active locale's equivalents.

        Args:
            label: The English label (e.g., "Fizz").

        Returns:
            The translated label.
        """
        return self.t(f"labels.{label}") or label

    def get_available_locales(self) -> list[str]:
        """Return a sorted list of all loaded locale codes."""
        return sorted(self._catalogs.keys())

    def get_locale_info(self) -> list[dict[str, str]]:
        """Return detailed info about all loaded locales.

        Returns a list of dicts suitable for displaying in a table,
        because enterprise software loves tables.
        """
        info = []
        for code in sorted(self._catalogs.keys()):
            catalog = self._catalogs[code]
            info.append({
                "code": code,
                "name": catalog.name,
                "fallback": catalog.fallback or "(none)",
                "keys": str(len(catalog.get_all_keys())),
                "plural_rule": catalog.plural_rule,
            })
        return info

    def get_catalog(self, locale: str) -> Optional[TranslationCatalog]:
        """Get a specific catalog by locale code."""
        return self._catalogs.get(locale)

    # Backwards-compatible aliases for the old TranslationService API
    def translate(self, key: str, locale: str, **kwargs: Any) -> str:
        """Translate a key to the specified locale (legacy API).

        Provided for backwards compatibility with code that used the
        old TranslationService.translate() method.
        """
        old_locale = self._active_locale
        try:
            if locale in self._catalogs:
                self._active_locale = locale
            return self.t(key, **kwargs)
        finally:
            self._active_locale = old_locale

    def get_supported_locales(self) -> list[str]:
        """Return all loaded locale codes (legacy API alias)."""
        return self.get_available_locales()


# Backwards compatibility alias
TranslationService = LocaleManager

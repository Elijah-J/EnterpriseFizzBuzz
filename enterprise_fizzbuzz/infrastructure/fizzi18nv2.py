"""
Enterprise FizzBuzz Platform - FizzI18nV2: Localization Management System

Centralized translation management with ICU message format, CLDR plural rules,
translation store, locale management, completion tracking, and export.

Architecture reference: ICU MessageFormat, CLDR, i18next, FormatJS.
"""

from __future__ import annotations

import copy
import json
import logging
import re
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzi18nv2 import (
    FizzI18nV2Error, FizzI18nV2TranslationNotFoundError, FizzI18nV2LocaleError,
    FizzI18nV2FormatError, FizzI18nV2PluralError, FizzI18nV2ExportError,
    FizzI18nV2ConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, FizzBuzzResult, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzi18nv2")

EVENT_I18N_TRANSLATED = EventType.register("FIZZI18NV2_TRANSLATED")

FIZZI18NV2_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 148


class PluralCategory(Enum):
    ZERO = "zero"
    ONE = "one"
    TWO = "two"
    FEW = "few"
    MANY = "many"
    OTHER = "other"


@dataclass
class FizzI18nV2Config:
    default_locale: str = "en"
    fallback_locale: str = "en"
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class TranslationKey:
    key: str = ""
    default_value: str = ""
    context: str = ""
    max_length: int = 0

@dataclass
class Translation:
    key: str = ""
    locale: str = ""
    value: str = ""
    plural_forms: Dict[PluralCategory, str] = field(default_factory=dict)
    reviewed: bool = False


# ============================================================
# Translation Store
# ============================================================

class TranslationStore:
    """Stores and retrieves translations by key and locale."""

    def __init__(self) -> None:
        self._translations: Dict[str, Dict[str, Translation]] = defaultdict(dict)  # key -> locale -> Translation
        self._keys: OrderedDict[str, TranslationKey] = OrderedDict()

    def add(self, translation: Translation) -> Translation:
        self._translations[translation.key][translation.locale] = translation
        if translation.key not in self._keys:
            self._keys[translation.key] = TranslationKey(
                key=translation.key, default_value=translation.value,
            )
        return translation

    def get(self, key: str, locale: str, count: Optional[int] = None) -> str:
        trans = self._translations.get(key, {}).get(locale)
        if trans is None:
            # Fallback to English
            trans = self._translations.get(key, {}).get("en")
        if trans is None:
            raise FizzI18nV2TranslationNotFoundError(key, locale)

        if count is not None and trans.plural_forms:
            category = self._get_plural_category(count, locale)
            return trans.plural_forms.get(category, trans.plural_forms.get(PluralCategory.OTHER, trans.value))

        return trans.value

    def list_keys(self) -> List[str]:
        return list(self._keys.keys())

    def list_locales(self) -> List[str]:
        locales = set()
        for key_translations in self._translations.values():
            locales.update(key_translations.keys())
        return sorted(locales)

    def get_completion(self, locale: str) -> float:
        if not self._keys:
            return 1.0
        total = len(self._keys)
        translated = sum(1 for key in self._keys if locale in self._translations.get(key, {}))
        return translated / total

    def export_locale(self, locale: str) -> Dict[str, str]:
        result = {}
        for key in self._keys:
            trans = self._translations.get(key, {}).get(locale)
            if trans:
                result[key] = trans.value
        return result

    def _get_plural_category(self, count: int, locale: str) -> PluralCategory:
        """CLDR-style plural category selection (English rules)."""
        if count == 0:
            return PluralCategory.ZERO
        elif count == 1:
            return PluralCategory.ONE
        elif count == 2:
            return PluralCategory.TWO
        else:
            return PluralCategory.OTHER


# ============================================================
# ICU Message Formatter
# ============================================================

class ICUMessageFormatter:
    """Formats ICU MessageFormat patterns with interpolation and plurals."""

    def format(self, pattern: str, values: Dict[str, Any]) -> str:
        # Simple interpolation: {name}
        result = pattern
        for key, val in values.items():
            result = result.replace(f"{{{key}}}", str(val))

        # Plural: {count, plural, one{# item} other{# items}}
        # Find the plural block by matching balanced braces
        plural_start = result.find(", plural,")
        if plural_start >= 0:
            # Walk back to find the opening {
            brace_pos = result.rfind("{", 0, plural_start)
            if brace_pos >= 0:
                var_name = result[brace_pos + 1:plural_start].strip()
                # Find matching closing brace
                depth = 1
                i = plural_start + len(", plural,")
                while i < len(result) and depth > 0:
                    if result[i] == "{": depth += 1
                    elif result[i] == "}": depth -= 1
                    i += 1
                plural_body = result[plural_start + len(", plural,"):i - 1].strip()

                count = values.get(var_name, 0)
                if not isinstance(count, (int, float)):
                    count = 0
                count = int(count)

                # Parse plural forms
                forms = {}
                form_pattern = re.compile(r'(\w+)\{([^}]*)\}')
                for form_match in form_pattern.finditer(plural_body):
                    category = form_match.group(1)
                    text = form_match.group(2)
                    forms[category] = text

                # Select form
                if count == 0 and "zero" in forms:
                    selected = forms["zero"]
                elif count == 1 and "one" in forms:
                    selected = forms["one"]
                elif count == 2 and "two" in forms:
                    selected = forms["two"]
                elif "other" in forms:
                    selected = forms["other"]
                else:
                    selected = str(count)

                selected = selected.replace("#", str(count))
                result = result[:brace_pos] + selected + result[i:]

        # Legacy regex approach for simpler patterns
        match = None
        plural_pattern = re.compile(r'\{(\w+),\s*plural,\s*(.*?)\}(?!\})', re.DOTALL)
        match = plural_pattern.search(result)
        if match:
            var_name = match.group(1)
            plural_body = match.group(2)
            count = values.get(var_name, 0)
            if not isinstance(count, (int, float)):
                count = 0
            count = int(count)

            # Parse plural forms
            forms = {}
            form_pattern = re.compile(r'(\w+)\{([^}]*)\}')
            for form_match in form_pattern.finditer(plural_body):
                category = form_match.group(1)
                text = form_match.group(2)
                forms[category] = text

            # Select form
            if count == 0 and "zero" in forms:
                selected = forms["zero"]
            elif count == 1 and "one" in forms:
                selected = forms["one"]
            elif count == 2 and "two" in forms:
                selected = forms["two"]
            elif "other" in forms:
                selected = forms["other"]
            else:
                selected = str(count)

            # Replace # with count
            selected = selected.replace("#", str(count))
            result = result[:match.start()] + selected + result[match.end():]

        return result


# ============================================================
# Locale Manager
# ============================================================

class LocaleManager:
    """Manages active locale and provides translation shortcuts."""

    def __init__(self, store: TranslationStore, formatter: Optional[ICUMessageFormatter] = None,
                 default_locale: str = "en") -> None:
        self._store = store
        self._formatter = formatter or ICUMessageFormatter()
        self._locale = default_locale

    def set_locale(self, locale: str) -> None:
        self._locale = locale

    def get_locale(self) -> str:
        return self._locale

    def t(self, key: str, **kwargs) -> str:
        """Translate a key with optional interpolation."""
        count = kwargs.pop("count", None)
        try:
            value = self._store.get(key, self._locale, count)
        except FizzI18nV2TranslationNotFoundError:
            # Return key as fallback
            return key

        if kwargs:
            value = self._formatter.format(value, kwargs)
        return value

    def available_locales(self) -> List[str]:
        return self._store.list_locales()


# ============================================================
# Dashboard & Middleware
# ============================================================

class FizzI18nV2Dashboard:
    def __init__(self, store: Optional[TranslationStore] = None,
                 locale_manager: Optional[LocaleManager] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._store = store
        self._locale_mgr = locale_manager
        self._width = width

    def render(self) -> str:
        lines = [
            "=" * self._width,
            "FizzI18nV2 Localization Dashboard".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZI18NV2_VERSION}",
        ]
        if self._store:
            lines.append(f"  Keys:    {len(self._store.list_keys())}")
            lines.append(f"  Locales: {', '.join(self._store.list_locales())}")
            for locale in self._store.list_locales():
                pct = self._store.get_completion(locale) * 100
                lines.append(f"  {locale}: {pct:.0f}% complete")
        if self._locale_mgr:
            lines.append(f"  Active:  {self._locale_mgr.get_locale()}")
        return "\n".join(lines)


class FizzI18nV2Middleware(IMiddleware):
    def __init__(self, store: Optional[TranslationStore] = None,
                 locale_manager: Optional[LocaleManager] = None,
                 dashboard: Optional[FizzI18nV2Dashboard] = None) -> None:
        self._store = store
        self._locale_mgr = locale_manager
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzi18nv2"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "FizzI18nV2 not initialized"

    def render_locales(self) -> str:
        if not self._store: return "No store"
        lines = ["FizzI18nV2 Locales:"]
        for locale in self._store.list_locales():
            pct = self._store.get_completion(locale) * 100
            lines.append(f"  {locale}: {pct:.0f}%")
        return "\n".join(lines)


# ============================================================
# Factory
# ============================================================

def create_fizzi18nv2_subsystem(
    default_locale: str = "en",
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[TranslationStore, LocaleManager, FizzI18nV2Dashboard, FizzI18nV2Middleware]:
    config = FizzI18nV2Config(default_locale=default_locale, dashboard_width=dashboard_width)
    store = TranslationStore()
    formatter = ICUMessageFormatter()
    locale_mgr = LocaleManager(store, formatter, default_locale)

    # Default English translations
    for key, value in [
        ("fizzbuzz.title", "Enterprise FizzBuzz Platform"),
        ("fizzbuzz.result", "Result"),
        ("fizzbuzz.fizz", "Fizz"),
        ("fizzbuzz.buzz", "Buzz"),
        ("fizzbuzz.fizzbuzz", "FizzBuzz"),
        ("fizzbuzz.evaluations", "evaluations"),
        ("fizzbuzz.modules_loaded", "modules loaded"),
    ]:
        store.add(Translation(key=key, locale="en", value=value))

    # Plural forms
    store.add(Translation(key="fizzbuzz.evaluations", locale="en",
                           value="{count} evaluations",
                           plural_forms={PluralCategory.ONE: "1 evaluation",
                                          PluralCategory.OTHER: "{count} evaluations",
                                          PluralCategory.ZERO: "no evaluations"}))

    # German translations
    for key, value in [
        ("fizzbuzz.title", "Enterprise FizzBuzz Plattform"),
        ("fizzbuzz.result", "Ergebnis"),
        ("fizzbuzz.fizz", "Fizz"),
        ("fizzbuzz.buzz", "Buzz"),
        ("fizzbuzz.fizzbuzz", "FizzBuzz"),
    ]:
        store.add(Translation(key=key, locale="de", value=value))

    # Japanese translations
    for key, value in [
        ("fizzbuzz.title", "Enterprise FizzBuzz Platform"),
        ("fizzbuzz.result", "Result"),
        ("fizzbuzz.fizz", "Fizz"),
    ]:
        store.add(Translation(key=key, locale="ja", value=value))

    dashboard = FizzI18nV2Dashboard(store, locale_mgr, dashboard_width)
    middleware = FizzI18nV2Middleware(store, locale_mgr, dashboard)

    logger.info("FizzI18nV2 initialized: %d keys, %d locales", len(store.list_keys()), len(store.list_locales()))
    return store, locale_mgr, dashboard, middleware

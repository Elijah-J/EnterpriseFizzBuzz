"""
Tests for the FizzI18nV2 Localization Management System.

Validates translation storage, ICU message formatting, locale management,
plural form resolution, completion tracking, dashboard rendering, and
middleware integration — ensuring that every FizzBuzz evaluation can be
delivered in the correct locale with full CLDR plural-rule compliance.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzi18nv2 import (
    FIZZI18NV2_VERSION,
    MIDDLEWARE_PRIORITY,
    PluralCategory,
    FizzI18nV2Config,
    TranslationKey,
    Translation,
    TranslationStore,
    ICUMessageFormatter,
    LocaleManager,
    FizzI18nV2Dashboard,
    FizzI18nV2Middleware,
    create_fizzi18nv2_subsystem,
)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all singletons between tests to prevent cross-contamination."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify module-level constants are correctly declared."""

    def test_version(self):
        assert FIZZI18NV2_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 148


# ---------------------------------------------------------------------------
# TestTranslationStore
# ---------------------------------------------------------------------------

class TestTranslationStore:
    """Verify the translation storage layer handles CRUD and queries."""

    def test_add_and_get_translation(self):
        store = TranslationStore()
        t = Translation(
            key="greeting",
            locale="en",
            value="Hello",
            plural_forms={},
            reviewed=True,
        )
        store.add(t)
        result = store.get("greeting", "en")
        assert result == "Hello"

    def test_get_with_plural_one(self):
        store = TranslationStore()
        t = Translation(
            key="item_count",
            locale="en",
            value="{count} items",
            plural_forms={
                PluralCategory.ONE: "{count} item",
                PluralCategory.OTHER: "{count} items",
            },
            reviewed=False,
        )
        store.add(t)
        result = store.get("item_count", "en", count=1)
        assert "item" in result
        assert "items" not in result

    def test_get_with_plural_other(self):
        store = TranslationStore()
        t = Translation(
            key="item_count",
            locale="en",
            value="{count} items",
            plural_forms={
                PluralCategory.ONE: "{count} item",
                PluralCategory.OTHER: "{count} items",
            },
            reviewed=False,
        )
        store.add(t)
        result = store.get("item_count", "en", count=5)
        assert "items" in result

    def test_list_keys(self):
        store = TranslationStore()
        store.add(Translation(key="a", locale="en", value="A", plural_forms={}, reviewed=True))
        store.add(Translation(key="b", locale="en", value="B", plural_forms={}, reviewed=True))
        keys = store.list_keys()
        assert "a" in keys
        assert "b" in keys

    def test_list_locales(self):
        store = TranslationStore()
        store.add(Translation(key="a", locale="en", value="A", plural_forms={}, reviewed=True))
        store.add(Translation(key="a", locale="de", value="A-de", plural_forms={}, reviewed=True))
        locales = store.list_locales()
        assert "en" in locales
        assert "de" in locales

    def test_completion_percentage(self):
        store = TranslationStore()
        store.add(Translation(key="a", locale="en", value="A", plural_forms={}, reviewed=True))
        store.add(Translation(key="b", locale="en", value="B", plural_forms={}, reviewed=True))
        store.add(Translation(key="a", locale="de", value="A-de", plural_forms={}, reviewed=True))
        # de has 1 of 2 keys translated
        completion = store.get_completion("de")
        assert 0.0 < completion < 1.0
        # en has 2 of 2 keys translated
        en_completion = store.get_completion("en")
        assert en_completion == pytest.approx(1.0)

    def test_export_locale(self):
        store = TranslationStore()
        store.add(Translation(key="x", locale="fr", value="X-fr", plural_forms={}, reviewed=True))
        store.add(Translation(key="y", locale="fr", value="Y-fr", plural_forms={}, reviewed=True))
        exported = store.export_locale("fr")
        assert isinstance(exported, dict)
        assert exported["x"] == "X-fr"
        assert exported["y"] == "Y-fr"


# ---------------------------------------------------------------------------
# TestICUMessageFormatter
# ---------------------------------------------------------------------------

class TestICUMessageFormatter:
    """Verify ICU MessageFormat-style pattern interpolation."""

    def test_simple_interpolation(self):
        formatter = ICUMessageFormatter()
        result = formatter.format("Hello {name}", {"name": "World"})
        assert result == "Hello World"

    def test_plural_one(self):
        formatter = ICUMessageFormatter()
        pattern = "{count, plural, one{# item} other{# items}}"
        result = formatter.format(pattern, {"count": 1})
        assert "1 item" in result
        assert "items" not in result

    def test_plural_other(self):
        formatter = ICUMessageFormatter()
        pattern = "{count, plural, one{# item} other{# items}}"
        result = formatter.format(pattern, {"count": 7})
        assert "7 items" in result

    def test_plural_zero(self):
        formatter = ICUMessageFormatter()
        pattern = "{count, plural, zero{no items} one{# item} other{# items}}"
        result = formatter.format(pattern, {"count": 0})
        assert "no items" in result or "0" in result


# ---------------------------------------------------------------------------
# TestLocaleManager
# ---------------------------------------------------------------------------

class TestLocaleManager:
    """Verify locale switching, translation lookup, and fallback behavior."""

    def _make_manager_with_store(self):
        store = TranslationStore()
        store.add(Translation(key="hello", locale="en", value="Hello", plural_forms={}, reviewed=True))
        store.add(Translation(key="hello", locale="de", value="Hallo", plural_forms={}, reviewed=True))
        store.add(Translation(key="greet", locale="en", value="Hi {name}", plural_forms={}, reviewed=True))
        manager = LocaleManager(store=store)
        return manager, store

    def test_set_and_get_locale(self):
        manager, _ = self._make_manager_with_store()
        manager.set_locale("de")
        assert manager.get_locale() == "de"

    def test_translate_key(self):
        manager, _ = self._make_manager_with_store()
        manager.set_locale("en")
        result = manager.t("hello")
        assert result == "Hello"

    def test_translate_other_locale(self):
        manager, _ = self._make_manager_with_store()
        manager.set_locale("de")
        result = manager.t("hello")
        assert result == "Hallo"

    def test_translate_with_interpolation(self):
        manager, _ = self._make_manager_with_store()
        manager.set_locale("en")
        result = manager.t("greet", name="Alice")
        assert "Alice" in result

    def test_fallback_to_default(self):
        manager, _ = self._make_manager_with_store()
        manager.set_locale("de")
        # "greet" only exists in en, not de — should fall back to default value
        result = manager.t("greet", name="Bob")
        assert result is not None
        assert len(result) > 0

    def test_available_locales(self):
        manager, _ = self._make_manager_with_store()
        locales = manager.available_locales()
        assert isinstance(locales, list)
        assert "en" in locales
        assert "de" in locales


# ---------------------------------------------------------------------------
# TestFizzI18nV2Dashboard
# ---------------------------------------------------------------------------

class TestFizzI18nV2Dashboard:
    """Verify dashboard rendering produces meaningful output."""

    def test_render_returns_string(self):
        store = TranslationStore()
        store.add(Translation(key="a", locale="en", value="A", plural_forms={}, reviewed=True))
        dashboard = FizzI18nV2Dashboard(store=store)
        rendered = dashboard.render()
        assert isinstance(rendered, str)
        assert len(rendered) > 0

    def test_render_contains_locale_info(self):
        store = TranslationStore()
        store.add(Translation(key="a", locale="en", value="A", plural_forms={}, reviewed=True))
        store.add(Translation(key="a", locale="ja", value="A-ja", plural_forms={}, reviewed=True))
        dashboard = FizzI18nV2Dashboard(store=store)
        rendered = dashboard.render()
        assert "en" in rendered


# ---------------------------------------------------------------------------
# TestFizzI18nV2Middleware
# ---------------------------------------------------------------------------

class TestFizzI18nV2Middleware:
    """Verify middleware integration with the processing pipeline."""

    def test_get_name(self):
        middleware = FizzI18nV2Middleware()
        assert middleware.get_name() == "fizzi18nv2"

    def test_get_priority(self):
        middleware = FizzI18nV2Middleware()
        assert middleware.get_priority() == 148

    def test_process_delegates_to_next(self):
        middleware = FizzI18nV2Middleware()
        ctx = MagicMock()
        next_handler = MagicMock()
        next_handler.return_value = ctx
        result = middleware.process(ctx, next_handler)
        next_handler.assert_called_once()
        assert result is not None


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    """Verify the factory function assembles all components correctly."""

    def test_returns_tuple_of_four(self):
        result = create_fizzi18nv2_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_components_have_correct_types(self):
        store, manager, dashboard, middleware = create_fizzi18nv2_subsystem()
        assert isinstance(store, TranslationStore)
        assert isinstance(manager, LocaleManager)
        assert isinstance(dashboard, FizzI18nV2Dashboard)
        assert isinstance(middleware, FizzI18nV2Middleware)

    def test_manager_has_available_locales(self):
        _, manager, _, _ = create_fizzi18nv2_subsystem()
        locales = manager.available_locales()
        assert isinstance(locales, list)
        assert len(locales) >= 1

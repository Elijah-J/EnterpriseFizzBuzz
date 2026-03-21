"""
Enterprise FizzBuzz Platform - Internationalization (i18n) Test Suite

Comprehensive tests for the i18n subsystem, including the proprietary
.fizztranslation parser, translation catalogs, pluralization engine,
locale resolver, locale manager singleton, and translation middleware.

Because untested internationalization is just wishful thinking with
Unicode characters.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ConfigurationManager, _SingletonMeta
from exceptions import (
    FizzTranslationParseError,
    LocaleChainExhaustedError,
    LocaleError,
    LocaleNotFoundError,
    PluralizationError,
    TranslationKeyError,
)
from i18n import (
    FizzTranslationParser,
    LocaleManager,
    LocaleResolver,
    PluralizationEngine,
    TranslationCatalog,
)
from middleware import MiddlewarePipeline, TranslationMiddleware
from models import FizzBuzzResult, ProcessingContext, RuleDefinition, RuleMatch
from plugins import PluginRegistry


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests to prevent cross-contamination."""
    _SingletonMeta.reset()
    PluginRegistry.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def parser():
    """A fresh parser instance for each test."""
    return FizzTranslationParser()


@pytest.fixture
def sample_locale_content():
    """Minimal .fizztranslation content in the new section-based format."""
    return """\
;; Test locale file
@locale = test
@name = Test Language
@fallback = en
@plural_rule = n != 1

[labels]
Fizz = Zapp
Buzz = Wham
FizzBuzz = ZappWham

[plurals]
Fizz.plural.one = Zapp
Fizz.plural.other = Zapps
Buzz.plural.one = Wham
Buzz.plural.other = Whams

[messages]
evaluating = Testing range [${start}, ${end}]...
strategy = Strat: ${name}

[banner]
subtitle = <<HEREDOC
    T E S T   E D I T I O N
HEREDOC
"""


@pytest.fixture
def en_locale_content():
    """English locale content in the new format."""
    return """\
@locale = en
@name = English
@plural_rule = n != 1

[labels]
Fizz = Fizz
Buzz = Buzz
FizzBuzz = FizzBuzz

[plurals]
Fizz.plural.one = Fizz
Fizz.plural.other = Fizzes
Buzz.plural.one = Buzz
Buzz.plural.other = Buzzes

[messages]
evaluating = Evaluating FizzBuzz for range [${start}, ${end}]...
strategy = Strategy: ${name}
greeting = Hello ${name}!
"""


@pytest.fixture
def locale_dir(sample_locale_content, en_locale_content):
    """Create a temporary directory with locale files for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write test locale
        test_path = Path(tmpdir) / "test.fizztranslation"
        test_path.write_text(sample_locale_content, encoding="utf-8")

        # Write English locale
        en_path = Path(tmpdir) / "en.fizztranslation"
        en_path.write_text(en_locale_content, encoding="utf-8")

        yield tmpdir


@pytest.fixture
def locale_manager(locale_dir):
    """A LocaleManager loaded with test locales."""
    mgr = LocaleManager()
    mgr.load_all(locale_dir)
    return mgr


@pytest.fixture
def config() -> ConfigurationManager:
    cfg = ConfigurationManager()
    cfg.load()
    return cfg


# ============================================================
# TranslationCatalog Tests
# ============================================================


class TestTranslationCatalog:
    def test_empty_catalog_defaults(self):
        cat = TranslationCatalog()
        assert cat.locale == "unknown"
        assert cat.name == "Unknown"
        assert cat.fallback is None
        assert cat.plural_rule == "n != 1"

    def test_set_and_get_metadata(self):
        cat = TranslationCatalog()
        cat.set_metadata("locale", "fr")
        cat.set_metadata("name", "Francais")
        assert cat.locale == "fr"
        assert cat.name == "Francais"

    def test_set_and_get_entry(self):
        cat = TranslationCatalog()
        cat.set_entry("labels", "Fizz", "Petillement")
        assert cat.get("labels.Fizz") == "Petillement"

    def test_get_returns_none_for_missing_key(self):
        cat = TranslationCatalog()
        assert cat.get("nonexistent.key") is None

    def test_interpolation(self):
        cat = TranslationCatalog()
        cat.set_entry("messages", "hello", "Bonjour ${name}!")
        result = cat.get("messages.hello", name="FizzBuzz")
        assert result == "Bonjour FizzBuzz!"

    def test_multiple_interpolation(self):
        cat = TranslationCatalog()
        cat.set_entry("messages", "range", "[${start}, ${end}]")
        result = cat.get("messages.range", start=1, end=100)
        assert result == "[1, 100]"

    def test_set_and_get_plural_entry(self):
        cat = TranslationCatalog()
        cat.set_plural_entry("plurals", "Fizz.plural", "one", "Fizz")
        cat.set_plural_entry("plurals", "Fizz.plural", "other", "Fizzes")
        assert cat.get_plural("plurals.Fizz.plural", 1, "one") == "Fizz"
        assert cat.get_plural("plurals.Fizz.plural", 5, "other") == "Fizzes"

    def test_plural_get_returns_none_for_missing(self):
        cat = TranslationCatalog()
        assert cat.get_plural("nonexistent", 1, "one") is None

    def test_has_key(self):
        cat = TranslationCatalog()
        cat.set_entry("labels", "Fizz", "Test")
        assert cat.has_key("labels.Fizz") is True
        assert cat.has_key("labels.Nope") is False

    def test_get_all_keys(self):
        cat = TranslationCatalog()
        cat.set_entry("labels", "Fizz", "A")
        cat.set_entry("labels", "Buzz", "B")
        keys = cat.get_all_keys()
        assert "labels.Fizz" in keys
        assert "labels.Buzz" in keys

    def test_fallback_none_string(self):
        """Metadata fallback='none' should resolve to None."""
        cat = TranslationCatalog()
        cat.set_metadata("fallback", "none")
        assert cat.fallback is None


# ============================================================
# FizzTranslationParser Tests
# ============================================================


class TestFizzTranslationParser:
    def test_parse_basic_file(self, parser, sample_locale_content):
        catalog = parser.parse_string(sample_locale_content)
        assert catalog.locale == "test"
        assert catalog.name == "Test Language"
        assert catalog.fallback == "en"

    def test_parse_labels(self, parser, sample_locale_content):
        catalog = parser.parse_string(sample_locale_content)
        assert catalog.get("labels.Fizz") == "Zapp"
        assert catalog.get("labels.Buzz") == "Wham"
        assert catalog.get("labels.FizzBuzz") == "ZappWham"

    def test_parse_messages_with_interpolation(self, parser, sample_locale_content):
        catalog = parser.parse_string(sample_locale_content)
        result = catalog.get("messages.evaluating", start=1, end=50)
        assert result == "Testing range [1, 50]..."

    def test_parse_heredoc(self, parser, sample_locale_content):
        catalog = parser.parse_string(sample_locale_content)
        subtitle = catalog.get("banner.subtitle")
        assert subtitle is not None
        assert "T E S T   E D I T I O N" in subtitle

    def test_parse_plural_entries(self, parser, sample_locale_content):
        catalog = parser.parse_string(sample_locale_content)
        assert catalog.get_plural("plurals.Fizz.plural", 1, "one") == "Zapp"
        assert catalog.get_plural("plurals.Fizz.plural", 5, "other") == "Zapps"

    def test_parse_comments_ignored(self, parser):
        content = """\
;; This is a comment
@locale = x
@name = X

[labels]
;; Another comment
Fizz = Test
"""
        catalog = parser.parse_string(content)
        assert catalog.get("labels.Fizz") == "Test"

    def test_parse_hash_comments_ignored(self, parser):
        content = """\
# This is a hash comment
@locale = x
@name = X

[labels]
# Another hash comment
Fizz = Test
"""
        catalog = parser.parse_string(content)
        assert catalog.get("labels.Fizz") == "Test"

    def test_parse_blank_lines_ignored(self, parser):
        content = """\
@locale = x
@name = X

[labels]

Fizz = Test

"""
        catalog = parser.parse_string(content)
        assert catalog.get("labels.Fizz") == "Test"

    def test_parse_unterminated_heredoc_raises(self, parser):
        content = """\
@locale = x
@name = X

[banner]
subtitle = <<END
This never ends
"""
        with pytest.raises(FizzTranslationParseError):
            parser.parse_string(content)

    def test_parse_metadata_extraction(self, parser):
        content = """\
@locale = ja
@name = Japanese
@plural_rule = 0
@version = 2.0

[labels]
Fizz = Test
"""
        catalog = parser.parse_string(content)
        assert catalog.locale == "ja"
        assert catalog.plural_rule == "0"
        assert catalog.metadata.get("version") == "2.0"

    def test_parse_file_from_disk(self, parser):
        """Test parsing an actual file from disk."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".fizztranslation",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write("@locale = disk\n@name = Disk Test\n\n[labels]\nFizz = DiskFizz\n")
            tmp_path = f.name

        try:
            catalog = parser.parse(tmp_path)
            assert catalog.locale == "disk"
            assert catalog.get("labels.Fizz") == "DiskFizz"
        finally:
            os.unlink(tmp_path)

    def test_parse_legacy_format(self, parser):
        """Test parsing the legacy @@/>> format for backwards compatibility."""
        content = """\
# Comment line
@@locale: legacy
@@name: Legacy Format
@@fallback: en
@@plural_rule: english

>> fizz.label = LegacyFizz
>> buzz.label = LegacyBuzz
>> fizzbuzz.label = LegacyFizzBuzz
>> summary.title = Legacy Summary
>> status.evaluating = Legacy evaluating [{start}, {end}]
"""
        catalog = parser.parse_string(content)
        assert catalog.locale == "legacy"
        assert catalog.name == "Legacy Format"
        assert catalog.get("labels.Fizz") == "LegacyFizz"
        assert catalog.get("labels.Buzz") == "LegacyBuzz"
        assert catalog.get("labels.FizzBuzz") == "LegacyFizzBuzz"
        assert catalog.get("summary.title") == "Legacy Summary"

    def test_parse_legacy_plurals(self, parser):
        """Test parsing pipe-delimited plural forms in legacy format."""
        content = """\
@@locale: lp
@@name: LegacyPlural
@@plural_rule: english

>> fizz.plural = {count} Fizz | {count} Fizzes
"""
        catalog = parser.parse_string(content)
        one = catalog.get_plural("plurals.Fizz.plural", 1, "one")
        other = catalog.get_plural("plurals.Fizz.plural", 5, "other")
        assert one is not None
        assert other is not None
        assert "Fizz" in one
        assert "Fizzes" in other

    def test_parse_actual_locale_files(self, parser):
        """Verify the parser can handle whatever format the actual locale files are in."""
        locale_dir = Path(__file__).parent.parent / "locales"
        if not locale_dir.exists():
            pytest.skip("Locale directory not found")

        for f in locale_dir.glob("*.fizztranslation"):
            catalog = parser.parse(str(f))
            assert catalog.locale != "unknown", f"Failed to parse locale from {f.name}"


# ============================================================
# PluralizationEngine Tests
# ============================================================


class TestPluralizationEngine:
    def setup_method(self):
        self.engine = PluralizationEngine()

    def test_english_singular(self):
        assert self.engine.get_form("en", 1) == "one"

    def test_english_plural(self):
        assert self.engine.get_form("en", 0) == "other"
        assert self.engine.get_form("en", 2) == "other"
        assert self.engine.get_form("en", 100) == "other"

    def test_french_zero_is_singular(self):
        assert self.engine.get_form("fr", 0) == "one"
        assert self.engine.get_form("fr", 1) == "one"

    def test_french_plural(self):
        assert self.engine.get_form("fr", 2) == "other"
        assert self.engine.get_form("fr", 100) == "other"

    def test_german_follows_english_rules(self):
        assert self.engine.get_form("de", 1) == "one"
        assert self.engine.get_form("de", 2) == "other"

    def test_klingon_follows_english_rules(self):
        assert self.engine.get_form("tlh", 1) == "one"
        assert self.engine.get_form("tlh", 0) == "other"

    def test_japanese_always_other(self):
        assert self.engine.get_form("ja", 0) == "other"
        assert self.engine.get_form("ja", 1) == "other"
        assert self.engine.get_form("ja", 100) == "other"

    def test_custom_rule_expression(self):
        assert self.engine.get_form("xx", 1, rule="n != 1") == "one"
        assert self.engine.get_form("xx", 5, rule="n != 1") == "other"

    def test_rule_zero_always_other(self):
        assert self.engine.get_form("xx", 1, rule="0") == "other"
        assert self.engine.get_form("xx", 0, rule="0") == "other"

    def test_named_rule_compatibility(self):
        """Test that named rules from legacy format are resolved."""
        assert self.engine.get_form("xx", 1, rule="english") == "one"
        assert self.engine.get_form("xx", 2, rule="english") == "other"
        assert self.engine.get_form("xx", 0, rule="french") == "one"
        assert self.engine.get_form("xx", 2, rule="french") == "other"
        assert self.engine.get_form("xx", 1, rule="japanese") == "other"

    def test_unknown_locale_defaults_to_n_not_1(self):
        """Unknown locales use the default n != 1 rule."""
        assert self.engine.get_form("xx", 1) == "one"
        assert self.engine.get_form("xx", 2) == "other"


# ============================================================
# LocaleResolver Tests
# ============================================================


class TestLocaleResolver:
    def setup_method(self):
        self.resolver = LocaleResolver()

    def _make_catalog(self, locale, fallback=None, entries=None):
        cat = TranslationCatalog()
        cat.set_metadata("locale", locale)
        if fallback:
            cat.set_metadata("fallback", fallback)
        for key, value in (entries or {}).items():
            section, entry_key = key.split(".", 1)
            cat.set_entry(section, entry_key, value)
        return cat

    def test_build_chain_simple(self):
        catalogs = {
            "fr": self._make_catalog("fr", fallback="en"),
            "en": self._make_catalog("en"),
        }
        chain = self.resolver.build_chain("fr", catalogs)
        assert chain == ["fr", "en"]

    def test_build_chain_no_fallback(self):
        catalogs = {
            "en": self._make_catalog("en"),
        }
        chain = self.resolver.build_chain("en", catalogs)
        assert chain == ["en"]

    def test_build_chain_adds_global_fallback(self):
        catalogs = {
            "de": self._make_catalog("de"),
            "en": self._make_catalog("en"),
        }
        chain = self.resolver.build_chain("de", catalogs)
        assert "en" in chain

    def test_build_chain_no_circular(self):
        """Fallback chains should not loop infinitely."""
        catalogs = {
            "a": self._make_catalog("a", fallback="b"),
            "b": self._make_catalog("b", fallback="a"),
            "en": self._make_catalog("en"),
        }
        chain = self.resolver.build_chain("a", catalogs)
        assert chain.count("a") == 1
        assert chain.count("b") == 1

    def test_resolve_found_in_primary(self):
        catalogs = {
            "fr": self._make_catalog("fr", entries={"labels.Fizz": "Petillement"}),
            "en": self._make_catalog("en", entries={"labels.Fizz": "Fizz"}),
        }
        result = self.resolver.resolve("fr", "labels.Fizz", catalogs)
        assert result == "Petillement"

    def test_resolve_falls_back_to_en(self):
        catalogs = {
            "fr": self._make_catalog("fr", fallback="en"),
            "en": self._make_catalog("en", entries={"labels.Fizz": "Fizz"}),
        }
        result = self.resolver.resolve("fr", "labels.Fizz", catalogs)
        assert result == "Fizz"

    def test_resolve_returns_none_when_not_found(self):
        catalogs = {
            "en": self._make_catalog("en"),
        }
        result = self.resolver.resolve("en", "nonexistent.key", catalogs)
        assert result is None

    def test_resolve_with_interpolation(self):
        catalogs = {
            "en": self._make_catalog("en", entries={"messages.hello": "Hi ${name}!"}),
        }
        result = self.resolver.resolve("en", "messages.hello", catalogs, name="World")
        assert result == "Hi World!"


# ============================================================
# LocaleManager Tests
# ============================================================


class TestLocaleManager:
    def test_singleton_behavior(self, locale_dir):
        mgr1 = LocaleManager()
        mgr1.load_all(locale_dir)
        mgr2 = LocaleManager()
        assert mgr1 is mgr2

    def test_reset_creates_new_instance(self, locale_dir):
        mgr1 = LocaleManager()
        mgr1.load_all(locale_dir)
        LocaleManager.reset()
        mgr2 = LocaleManager()
        assert mgr1 is not mgr2

    def test_load_all_populates_catalogs(self, locale_manager):
        locales = locale_manager.get_available_locales()
        assert "en" in locales
        assert "test" in locales

    def test_set_locale(self, locale_manager):
        locale_manager.set_locale("test")
        assert locale_manager.active_locale == "test"

    def test_set_locale_not_found_raises(self, locale_manager):
        with pytest.raises(LocaleNotFoundError):
            locale_manager.set_locale("nonexistent")

    def test_t_basic_translation(self, locale_manager):
        locale_manager.set_locale("test")
        result = locale_manager.t("labels.Fizz")
        assert result == "Zapp"

    def test_t_with_interpolation(self, locale_manager):
        locale_manager.set_locale("test")
        result = locale_manager.t("messages.evaluating", start=1, end=50)
        assert result == "Testing range [1, 50]..."

    def test_t_falls_back_to_en(self, locale_manager):
        locale_manager.set_locale("test")
        # "greeting" exists only in en
        result = locale_manager.t("messages.greeting", name="World")
        assert result == "Hello World!"

    def test_t_returns_key_on_missing(self, locale_manager):
        result = locale_manager.t("totally.missing.key")
        assert result == "totally.missing.key"

    def test_t_strict_mode_raises(self, locale_manager):
        locale_manager.set_strict_mode(True)
        with pytest.raises(TranslationKeyError):
            locale_manager.t("totally.missing.key")

    def test_tp_pluralization(self, locale_manager):
        locale_manager.set_locale("test")
        one = locale_manager.tp("plurals.Fizz.plural", 1)
        other = locale_manager.tp("plurals.Fizz.plural", 5)
        assert one == "Zapp"
        assert other == "Zapps"

    def test_get_label(self, locale_manager):
        locale_manager.set_locale("test")
        assert locale_manager.get_label("Fizz") == "Zapp"
        assert locale_manager.get_label("Buzz") == "Wham"
        assert locale_manager.get_label("FizzBuzz") == "ZappWham"

    def test_get_label_english(self, locale_manager):
        locale_manager.set_locale("en")
        assert locale_manager.get_label("Fizz") == "Fizz"

    def test_get_locale_info(self, locale_manager):
        info = locale_manager.get_locale_info()
        assert len(info) >= 2
        codes = [i["code"] for i in info]
        assert "en" in codes
        assert "test" in codes

    def test_get_catalog(self, locale_manager):
        cat = locale_manager.get_catalog("en")
        assert cat is not None
        assert cat.locale == "en"

    def test_get_catalog_missing(self, locale_manager):
        assert locale_manager.get_catalog("nonexistent") is None

    def test_load_nonexistent_directory(self):
        mgr = LocaleManager()
        mgr.load_all("/nonexistent/path/that/does/not/exist")
        assert mgr.is_loaded is True
        assert len(mgr.get_available_locales()) == 0

    def test_default_locale_is_en(self):
        mgr = LocaleManager()
        assert mgr.active_locale == "en"

    def test_backwards_compat_translate(self, locale_manager):
        """Test the legacy translate() method."""
        result = locale_manager.translate("labels.Fizz", "test")
        assert result == "Zapp"

    def test_backwards_compat_get_supported_locales(self, locale_manager):
        locales = locale_manager.get_supported_locales()
        assert "en" in locales


# ============================================================
# TranslationMiddleware Tests
# ============================================================


class TestTranslationMiddleware:
    def _make_context_with_result(self, number, output, matched_labels=None):
        """Create a ProcessingContext with a FizzBuzzResult."""
        matched_rules = []
        if matched_labels:
            for label in matched_labels:
                rule_def = RuleDefinition(name=label, divisor=3, label=label)
                matched_rules.append(RuleMatch(rule=rule_def, number=number))

        result = FizzBuzzResult(
            number=number,
            output=output,
            matched_rules=matched_rules,
        )
        ctx = ProcessingContext(number=number, session_id="test-session")
        ctx.results = [result]
        return ctx

    def test_translates_fizz_label(self, locale_manager):
        locale_manager.set_locale("test")
        mw = TranslationMiddleware(locale_manager=locale_manager)
        ctx = self._make_context_with_result(3, "Fizz", ["Fizz"])
        result = mw.process(ctx, lambda c: c)
        assert result.results[-1].output == "Zapp"

    def test_translates_buzz_label(self, locale_manager):
        locale_manager.set_locale("test")
        mw = TranslationMiddleware(locale_manager=locale_manager)
        ctx = self._make_context_with_result(5, "Buzz", ["Buzz"])
        result = mw.process(ctx, lambda c: c)
        assert result.results[-1].output == "Wham"

    def test_translates_fizzbuzz_label(self, locale_manager):
        locale_manager.set_locale("test")
        mw = TranslationMiddleware(locale_manager=locale_manager)
        ctx = self._make_context_with_result(15, "FizzBuzz", ["Fizz", "Buzz"])
        result = mw.process(ctx, lambda c: c)
        assert result.results[-1].output == "ZappWham"

    def test_preserves_original_output_in_metadata(self, locale_manager):
        locale_manager.set_locale("test")
        mw = TranslationMiddleware(locale_manager=locale_manager)
        ctx = self._make_context_with_result(3, "Fizz", ["Fizz"])
        result = mw.process(ctx, lambda c: c)
        assert result.results[-1].metadata.get("original_output") == "Fizz"

    def test_adds_locale_to_metadata(self, locale_manager):
        locale_manager.set_locale("test")
        mw = TranslationMiddleware(locale_manager=locale_manager)
        ctx = self._make_context_with_result(3, "Fizz", ["Fizz"])
        result = mw.process(ctx, lambda c: c)
        assert result.results[-1].metadata.get("locale") == "test"

    def test_numbers_pass_through_unchanged(self, locale_manager):
        locale_manager.set_locale("test")
        mw = TranslationMiddleware(locale_manager=locale_manager)
        ctx = self._make_context_with_result(7, "7")
        result = mw.process(ctx, lambda c: c)
        assert result.results[-1].output == "7"

    def test_english_locale_no_translation_change(self, locale_manager):
        locale_manager.set_locale("en")
        mw = TranslationMiddleware(locale_manager=locale_manager)
        ctx = self._make_context_with_result(3, "Fizz", ["Fizz"])
        result = mw.process(ctx, lambda c: c)
        assert result.results[-1].output == "Fizz"

    def test_get_name(self):
        mw = TranslationMiddleware()
        assert mw.get_name() == "TranslationMiddleware"

    def test_get_priority(self):
        mw = TranslationMiddleware()
        assert mw.get_priority() == 50

    def test_middleware_in_pipeline(self, locale_manager):
        locale_manager.set_locale("test")
        mw = TranslationMiddleware(locale_manager=locale_manager)
        pipeline = MiddlewarePipeline()
        pipeline.add(mw)

        ctx = self._make_context_with_result(3, "Fizz", ["Fizz"])

        def handler(c):
            return c

        result = pipeline.execute(ctx, handler)
        assert result.results[-1].output == "Zapp"


# ============================================================
# Exception Tests
# ============================================================


class TestI18nExceptions:
    def test_locale_error_base(self):
        err = LocaleError("test error")
        assert "EFP-I000" in str(err)

    def test_locale_not_found_error(self):
        err = LocaleNotFoundError("klingon", searched_paths=["./locales"])
        assert "EFP-I001" in str(err)
        assert "klingon" in str(err)

    def test_translation_key_error(self):
        err = TranslationKeyError("labels.Fizz", "fr", ["fr", "en"])
        assert "EFP-I002" in str(err)
        assert "labels.Fizz" in str(err)

    def test_fizz_translation_parse_error(self):
        err = FizzTranslationParseError("test.fizztranslation", 42, "bad line")
        assert "EFP-I003" in str(err)
        assert "42" in str(err)

    def test_pluralization_error(self):
        err = PluralizationError("xx", 5, "bad_rule")
        assert "EFP-I004" in str(err)

    def test_locale_chain_exhausted_error(self):
        err = LocaleChainExhaustedError(chain=["fr", "en"])
        assert "EFP-I005" in str(err)


# ============================================================
# Config i18n Properties Tests
# ============================================================


class TestI18nConfig:
    def test_config_i18n_enabled(self, config):
        assert config.i18n_enabled is True

    def test_config_i18n_locale(self, config):
        assert config.i18n_locale == "en"

    def test_config_i18n_strict_mode(self, config):
        assert config.i18n_strict_mode is False

    def test_config_i18n_fallback_chain(self, config):
        chain = config.i18n_fallback_chain
        assert isinstance(chain, list)
        assert "en" in chain

    def test_config_i18n_log_missing_keys(self, config):
        assert config.i18n_log_missing_keys is True

    def test_config_i18n_locale_directory(self, config):
        assert config.i18n_locale_directory == "./locales"


# ============================================================
# CLI Tests
# ============================================================


class TestCLILocaleFlag:
    def test_locale_flag_accepted(self):
        from main import build_argument_parser

        parser = build_argument_parser()
        args = parser.parse_args(["--locale", "de"])
        assert args.locale == "de"

    def test_locale_flag_default_is_none(self):
        from main import build_argument_parser

        parser = build_argument_parser()
        args = parser.parse_args([])
        assert args.locale is None

    def test_list_locales_flag(self):
        from main import build_argument_parser

        parser = build_argument_parser()
        args = parser.parse_args(["--list-locales"])
        assert args.list_locales is True

    def test_list_locales_flag_default(self):
        from main import build_argument_parser

        parser = build_argument_parser()
        args = parser.parse_args([])
        assert args.list_locales is False


# ============================================================
# Integration Tests
# ============================================================


class TestI18nIntegration:
    def test_load_actual_locale_files(self):
        """Test loading the actual locale files shipped with the project."""
        locale_dir = str(Path(__file__).parent.parent / "locales")
        if not Path(locale_dir).exists():
            pytest.skip("Locale directory not found")

        mgr = LocaleManager()
        mgr.load_all(locale_dir)
        locales = mgr.get_available_locales()
        assert len(locales) >= 1

    def test_full_translation_pipeline(self, locale_manager):
        """Test the complete translation flow: load -> set -> translate."""
        locale_manager.set_locale("test")

        # Basic label
        assert locale_manager.get_label("Fizz") == "Zapp"

        # Interpolated message
        msg = locale_manager.t("messages.evaluating", start=1, end=100)
        assert "1" in msg
        assert "100" in msg

        # Fallback to English
        greeting = locale_manager.t("messages.greeting", name="Enterprise")
        assert "Hello" in greeting

    def test_middleware_preserves_plain_numbers(self, locale_manager):
        """Numbers should never be translated, even in non-English locales."""
        locale_manager.set_locale("test")
        mw = TranslationMiddleware(locale_manager=locale_manager)

        for num in [1, 2, 4, 7, 8, 11, 13, 14]:
            ctx = ProcessingContext(number=num, session_id="test")
            result = FizzBuzzResult(number=num, output=str(num))
            ctx.results = [result]

            processed = mw.process(ctx, lambda c: c)
            assert processed.results[-1].output == str(num)

    def test_full_pipeline_with_service(self, locale_dir, config):
        """Full pipeline: build service with translation middleware."""
        from fizzbuzz_service import FizzBuzzServiceBuilder

        LocaleManager.reset()
        mgr = LocaleManager()
        mgr.load_all(locale_dir)
        mgr.set_locale("test")

        service = (
            FizzBuzzServiceBuilder()
            .with_config(config)
            .with_locale_manager(mgr)
            .with_default_middleware()
            .with_middleware(TranslationMiddleware(locale_manager=mgr))
            .build()
        )

        results = service.run(1, 15)
        outputs = [r.output for r in results]

        # Number 3 -> Zapp (Test locale Fizz)
        assert outputs[2] == "Zapp"
        # Number 5 -> Wham (Test locale Buzz)
        assert outputs[4] == "Wham"
        # Number 15 -> ZappWham (Test locale FizzBuzz)
        assert outputs[14] == "ZappWham"
        # Plain numbers stay the same
        assert outputs[0] == "1"

    def test_english_pipeline_unchanged(self, config):
        """English locale should produce standard FizzBuzz output."""
        from fizzbuzz_service import FizzBuzzServiceBuilder

        service = (
            FizzBuzzServiceBuilder()
            .with_config(config)
            .with_default_middleware()
            .build()
        )

        results = service.run(1, 15)
        assert results[2].output == "Fizz"
        assert results[4].output == "Buzz"
        assert results[14].output == "FizzBuzz"


# ============================================================
# Exception Aliases Tests
# ============================================================


class TestExceptionAliases:
    def test_backwards_compat_aliases(self):
        """Test that backwards compatibility aliases exist."""
        from exceptions import (
            LocalizationError,
            TranslationFileParseError,
            TranslationKeyMissingError,
            PluralizationRuleError,
        )
        assert LocalizationError is LocaleError
        assert TranslationKeyMissingError is TranslationKeyError
        assert PluralizationRuleError is PluralizationError

    def test_translation_service_alias(self):
        """Test that TranslationService is an alias for LocaleManager."""
        from i18n import TranslationService
        assert TranslationService is LocaleManager

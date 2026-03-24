"""Feature descriptor for the Internationalization (i18n) subsystem."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class I18nFeature(FeatureDescriptor):
    name = "i18n"
    description = "Internationalization with 7 locales including Klingon, Sindarin, and Quenya"
    middleware_priority = 6
    cli_flags = [
        ("--locale", {"type": str, "metavar": "LOCALE", "default": None,
                      "help": "Locale for internationalized output (en, de, fr, ja, tlh, sjn, qya)"}),
        ("--list-locales", {"action": "store_true", "default": False,
                            "help": "Display available locales and exit"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            bool(getattr(args, "locale", None)),
            getattr(args, "list_locales", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return getattr(args, "list_locales", False)

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.i18n import LocaleManager

        if not config.i18n_enabled:
            print("\n  i18n is disabled. Enable it in config.yaml.\n")
            return 0

        LocaleManager.reset()
        locale_mgr = LocaleManager()
        locale_dir = str(Path(config.i18n_locale_directory))
        locale_mgr.load_all(locale_dir)

        info = locale_mgr.get_locale_info()
        print("\n  Available Locales:")
        print("  " + "-" * 60)
        print(f"  {'Code':<8} {'Name':<20} {'Fallback':<12} {'Keys':<8} {'Plural Rule'}")
        print("  " + "-" * 60)
        for loc in info:
            print(
                f"  {loc['code']:<8} {loc['name']:<20} {loc['fallback']:<12} "
                f"{loc['keys']:<8} {loc['plural_rule']}"
            )
        print("  " + "-" * 60)
        print()
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.i18n import LocaleManager
        from enterprise_fizzbuzz.infrastructure.middleware import TranslationMiddleware

        if not config.i18n_enabled:
            return None, None

        locale = args.locale or config.i18n_locale

        LocaleManager.reset()
        locale_mgr = LocaleManager()
        locale_dir = str(Path(config.i18n_locale_directory))
        locale_mgr.load_all(locale_dir)
        locale_mgr.set_strict_mode(config.i18n_strict_mode)

        if locale in locale_mgr.get_available_locales():
            locale_mgr.set_locale(locale)
        elif locale != "en":
            print(f"  Warning: locale '{locale}' not available, using 'en'")

        middleware = TranslationMiddleware(locale_manager=locale_mgr)
        return locale_mgr, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None

"""Enterprise FizzBuzz Platform - FizzI18nV2 Errors (EFP-I18N2-00 .. EFP-I18N2-06)"""
from __future__ import annotations
from ._base import FizzBuzzError

class FizzI18nV2Error(FizzBuzzError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"FizzI18nV2 error: {reason}", error_code="EFP-I18N2-00", context={"reason": reason})
class FizzI18nV2TranslationNotFoundError(FizzI18nV2Error):
    def __init__(self, key: str, locale: str) -> None:
        super().__init__(f"Translation not found: {key} [{locale}]"); self.error_code = "EFP-I18N2-01"
class FizzI18nV2LocaleError(FizzI18nV2Error):
    def __init__(self, locale: str, reason: str) -> None:
        super().__init__(f"Locale {locale}: {reason}"); self.error_code = "EFP-I18N2-02"
class FizzI18nV2FormatError(FizzI18nV2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Format: {reason}"); self.error_code = "EFP-I18N2-03"
class FizzI18nV2PluralError(FizzI18nV2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Plural: {reason}"); self.error_code = "EFP-I18N2-04"
class FizzI18nV2ExportError(FizzI18nV2Error):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Export: {reason}"); self.error_code = "EFP-I18N2-05"
class FizzI18nV2ConfigError(FizzI18nV2Error):
    def __init__(self, param: str, reason: str) -> None:
        super().__init__(f"Config {param}: {reason}"); self.error_code = "EFP-I18N2-06"

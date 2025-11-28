"""Internationalization (i18n) support for AirBorne.

This module provides translation loading and lookup for UI strings.
Translations are stored in config/i18n/{language}.yaml files.

Typical usage:
    from airborne.core.i18n import get_translator, t

    # Get translator instance
    translator = get_translator()

    # Translate a string
    translated = t("menu.main.title")  # Returns translated string

    # Change language
    translator.set_language("fr")
"""

import logging
from typing import Any

import yaml

from airborne.core.resource_path import get_config_path

logger = logging.getLogger(__name__)

# Supported languages with display names
SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "fr": "Francais",
}

DEFAULT_LANGUAGE = "en"


class Translator:
    """Manages translations for the application.

    Loads translation files from config/i18n/ and provides lookup
    functionality with fallback to English.

    Attributes:
        language: Current language code (e.g., "en", "fr").
        translations: Loaded translations dictionary.
    """

    def __init__(self) -> None:
        """Initialize translator with default language."""
        self._language = DEFAULT_LANGUAGE
        self._translations: dict[str, dict[str, Any]] = {}
        self._load_translations()

    @property
    def language(self) -> str:
        """Get current language code."""
        return self._language

    def set_language(self, language: str) -> bool:
        """Set the current language.

        Args:
            language: Language code (e.g., "en", "fr").

        Returns:
            True if language was changed successfully.
        """
        if language not in SUPPORTED_LANGUAGES:
            logger.warning("Unsupported language: %s", language)
            return False

        if language != self._language:
            self._language = language
            logger.info("Language changed to: %s", language)

        return True

    def get_supported_languages(self) -> dict[str, str]:
        """Get supported languages.

        Returns:
            Dictionary of language code -> display name.
        """
        return SUPPORTED_LANGUAGES.copy()

    def _load_translations(self) -> None:
        """Load all translation files."""
        for lang_code in SUPPORTED_LANGUAGES:
            self._load_language(lang_code)

    def _load_language(self, lang_code: str) -> bool:
        """Load translations for a specific language.

        Args:
            lang_code: Language code to load.

        Returns:
            True if loaded successfully.
        """
        try:
            i18n_path = get_config_path(f"i18n/{lang_code}.yaml")
            if not i18n_path.exists():
                logger.debug("Translation file not found: %s", i18n_path)
                return False

            with open(i18n_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if data:
                self._translations[lang_code] = data
                logger.info("Loaded translations for: %s", lang_code)
                return True

        except Exception as e:
            logger.error("Failed to load translations for %s: %s", lang_code, e)

        return False

    def reload(self) -> None:
        """Reload all translation files."""
        self._translations.clear()
        self._load_translations()

    def translate(self, key: str, **kwargs: Any) -> str:
        """Translate a key to the current language.

        Args:
            key: Dot-separated translation key (e.g., "menu.main.title").
            **kwargs: Optional format arguments for string interpolation.

        Returns:
            Translated string, or key if not found.
        """
        # Try current language
        result = self._lookup(key, self._language)

        # Fallback to English if not found
        if result is None and self._language != DEFAULT_LANGUAGE:
            result = self._lookup(key, DEFAULT_LANGUAGE)

        # Return key if still not found
        if result is None:
            logger.debug("Translation not found: %s", key)
            return key

        # Apply format arguments if provided
        if kwargs:
            try:
                result = result.format(**kwargs)
            except KeyError as e:
                logger.warning("Format key missing in translation %s: %s", key, e)

        return result

    def _lookup(self, key: str, lang_code: str) -> str | None:
        """Look up a translation key in a specific language.

        Args:
            key: Dot-separated translation key.
            lang_code: Language code to look up.

        Returns:
            Translation string or None if not found.
        """
        if lang_code not in self._translations:
            return None

        # Navigate the nested dictionary using dot notation
        parts = key.split(".")
        current: Any = self._translations[lang_code]

        for part in parts:
            if not isinstance(current, dict):
                return None
            if part not in current:
                return None
            current = current[part]

        if isinstance(current, str):
            return current

        return None

    def has_key(self, key: str) -> bool:
        """Check if a translation key exists.

        Args:
            key: Translation key to check.

        Returns:
            True if key exists in current or fallback language.
        """
        if self._lookup(key, self._language) is not None:
            return True
        if self._language != DEFAULT_LANGUAGE:
            return self._lookup(key, DEFAULT_LANGUAGE) is not None
        return False


# Global translator instance
_translator: Translator | None = None


def get_translator() -> Translator:
    """Get the global translator instance.

    Returns:
        Translator instance.
    """
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator


def t(key: str, **kwargs: Any) -> str:
    """Translate a key using the global translator.

    Shorthand for get_translator().translate(key, **kwargs).

    Args:
        key: Translation key.
        **kwargs: Format arguments.

    Returns:
        Translated string.
    """
    return get_translator().translate(key, **kwargs)


def set_language(language: str) -> bool:
    """Set the global language.

    Args:
        language: Language code.

    Returns:
        True if successful.
    """
    return get_translator().set_language(language)


def get_language() -> str:
    """Get the current global language.

    Returns:
        Current language code.
    """
    return get_translator().language


def reload_translations() -> None:
    """Reload all translation files."""
    get_translator().reload()

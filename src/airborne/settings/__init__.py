"""User settings management for AirBorne.

This package provides persistent user settings storage for preferences
that should be saved across sessions, such as TTS voice selections.
"""

from airborne.settings.tts_settings import (
    VOICE_CATEGORIES,
    TTSSettings,
    VoiceCategorySettings,
    get_tts_settings,
    reset_tts_settings,
)

__all__ = [
    "TTSSettings",
    "VoiceCategorySettings",
    "VOICE_CATEGORIES",
    "get_tts_settings",
    "reset_tts_settings",
]

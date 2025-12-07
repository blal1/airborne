"""User settings management for AirBorne.

This package provides persistent user settings storage for preferences
that should be saved across sessions, such as TTS voice selections.
"""

from airborne.settings.atc_v2_settings import (
    PROVIDER_LOCAL,
    PROVIDER_REMOTE,
    ATCV2Settings,
    get_atc_v2_settings,
    reset_atc_v2_settings,
)
from airborne.settings.audio_settings import (
    VOLUME_CATEGORIES as AUDIO_VOLUME_CATEGORIES,
    AudioSettings,
    get_audio_settings,
    reset_audio_settings,
)
from airborne.settings.tts_settings import (
    VOICE_CATEGORIES,
    TTSSettings,
    VoiceCategorySettings,
    get_tts_settings,
    reset_tts_settings,
)

__all__ = [
    # TTS settings
    "TTSSettings",
    "VoiceCategorySettings",
    "VOICE_CATEGORIES",
    "get_tts_settings",
    "reset_tts_settings",
    # Audio settings
    "AudioSettings",
    "AUDIO_VOLUME_CATEGORIES",
    "get_audio_settings",
    "reset_audio_settings",
    # ATC V2 settings
    "ATCV2Settings",
    "PROVIDER_LOCAL",
    "PROVIDER_REMOTE",
    "get_atc_v2_settings",
    "reset_atc_v2_settings",
]

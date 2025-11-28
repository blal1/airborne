"""TTS voice settings management.

This module manages TTS voice preferences for different voice categories
(ui, cockpit, atc, atis, ground, tower, approach, departure, center).

Settings are stored in ~/.airborne/settings.json.

Typical usage:
    from airborne.settings import get_tts_settings

    settings = get_tts_settings()
    settings.set_voice("cockpit", "Samantha", "apple", 180)
    settings.save()

    # Get voice for a category
    voice = settings.get_voice("cockpit")
    print(f"Voice: {voice.voice_name}, Rate: {voice.rate}")
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Voice categories used in the simulator
VOICE_CATEGORIES = [
    "ui",  # Menu and UI announcements
    "cockpit",  # Cockpit readouts (altitude, speed, etc.)
    "atc",  # Generic ATC (fallback)
    "atis",  # Automated weather broadcasts
    "ground",  # Ground control
    "tower",  # Tower control
    "approach",  # Approach control
    "departure",  # Departure control
    "center",  # Center/ARTCC en-route control
]

# TTS modes
TTS_MODE_REALTIME = "realtime"  # Generate TTS in real-time
TTS_MODE_SELFVOICED = "selfvoiced"  # Use pre-recorded audio files

# Default voice settings per category (Apple TTS voices)
# English defaults
DEFAULT_VOICES_EN: dict[str, dict[str, Any]] = {
    "ui": {"voice_name": "Samantha", "engine": "apple", "rate": 200},
    "cockpit": {"voice_name": "Samantha", "engine": "apple", "rate": 220},
    "atc": {"voice_name": "Tom", "engine": "apple", "rate": 180},
    "atis": {"voice_name": "Karen", "engine": "apple", "rate": 160},
    "ground": {"voice_name": "Daniel", "engine": "apple", "rate": 175},
    "tower": {"voice_name": "Tom", "engine": "apple", "rate": 180},
    "approach": {"voice_name": "Alex", "engine": "apple", "rate": 175},
    "departure": {"voice_name": "Evan", "engine": "apple", "rate": 180},
    "center": {"voice_name": "Oliver", "engine": "apple", "rate": 170},
}

# French defaults
DEFAULT_VOICES_FR: dict[str, dict[str, Any]] = {
    "ui": {"voice_name": "Amélie", "engine": "apple", "rate": 200},
    "cockpit": {"voice_name": "Amélie", "engine": "apple", "rate": 220},
    "atc": {"voice_name": "Thomas", "engine": "apple", "rate": 180},
    "atis": {"voice_name": "Audrey", "engine": "apple", "rate": 160},
    "ground": {"voice_name": "Jacques", "engine": "apple", "rate": 175},
    "tower": {"voice_name": "Thomas", "engine": "apple", "rate": 180},
    "approach": {"voice_name": "Jacques", "engine": "apple", "rate": 175},
    "departure": {"voice_name": "Thomas", "engine": "apple", "rate": 180},
    "center": {"voice_name": "Jacques", "engine": "apple", "rate": 170},
}

# Default voices by language
DEFAULT_VOICES_BY_LANG: dict[str, dict[str, dict[str, Any]]] = {
    "en": DEFAULT_VOICES_EN,
    "fr": DEFAULT_VOICES_FR,
}

# Legacy: use English as default
DEFAULT_VOICES = DEFAULT_VOICES_EN


@dataclass
class VoiceCategorySettings:
    """Settings for a single voice category.

    Attributes:
        voice_name: Name of the TTS voice (e.g., "Samantha").
        engine: TTS engine name (e.g., "apple", "edge", "kokoro").
        rate: Speech rate in words per minute (typically 100-300).
    """

    voice_name: str
    engine: str = "apple"
    rate: int = 180

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VoiceCategorySettings":
        """Create from dictionary."""
        return cls(
            voice_name=data.get("voice_name", "Samantha"),
            engine=data.get("engine", "apple"),
            rate=data.get("rate", 180),
        )


@dataclass
class TTSSettings:
    """TTS settings manager with persistence.

    Manages voice settings for all voice categories and provides
    load/save functionality to ~/.airborne/settings.json.

    Attributes:
        mode: TTS mode ("realtime" or "selfvoiced").
        language: Preferred language code (e.g., "en", "fr").
        voices: Dictionary of voice category -> settings.
    """

    mode: str = TTS_MODE_REALTIME
    language: str = "en"
    voices: dict[str, VoiceCategorySettings] = field(default_factory=dict)
    _settings_path: Path = field(
        default_factory=lambda: Path.home() / ".airborne" / "settings.json"
    )
    _dirty: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize default voices for any missing categories."""
        for category in VOICE_CATEGORIES:
            if category not in self.voices:
                defaults = DEFAULT_VOICES.get(category, DEFAULT_VOICES["atc"])
                self.voices[category] = VoiceCategorySettings(
                    voice_name=defaults["voice_name"],
                    engine=defaults["engine"],
                    rate=defaults["rate"],
                )

    def get_voice(self, category: str) -> VoiceCategorySettings:
        """Get voice settings for a category.

        Args:
            category: Voice category name (e.g., "cockpit", "tower").

        Returns:
            VoiceCategorySettings for the category.
            Falls back to "atc" defaults if category unknown.
        """
        if category in self.voices:
            return self.voices[category]

        # Fallback to ATC defaults for unknown categories
        defaults = DEFAULT_VOICES.get(
            "atc", {"voice_name": "Samantha", "engine": "apple", "rate": 180}
        )
        return VoiceCategorySettings(
            voice_name=defaults["voice_name"],
            engine=defaults["engine"],
            rate=defaults["rate"],
        )

    def set_voice(
        self,
        category: str,
        voice_name: str,
        engine: str = "apple",
        rate: int | None = None,
    ) -> None:
        """Set voice for a category.

        Args:
            category: Voice category name.
            voice_name: TTS voice name.
            engine: TTS engine name.
            rate: Speech rate (uses existing rate if None).
        """
        if category not in self.voices:
            defaults = DEFAULT_VOICES.get(category, DEFAULT_VOICES["atc"])
            self.voices[category] = VoiceCategorySettings(
                voice_name=voice_name,
                engine=engine,
                rate=rate if rate is not None else defaults["rate"],
            )
        else:
            self.voices[category].voice_name = voice_name
            self.voices[category].engine = engine
            if rate is not None:
                self.voices[category].rate = rate
        self._dirty = True

    def set_rate(self, category: str, rate: int) -> None:
        """Set speech rate for a category.

        Args:
            category: Voice category name.
            rate: Speech rate in WPM (typically 100-300).
        """
        if category in self.voices:
            self.voices[category].rate = rate
            self._dirty = True

    def set_mode(self, mode: str) -> None:
        """Set TTS mode.

        Args:
            mode: "realtime" or "selfvoiced".
        """
        if mode in (TTS_MODE_REALTIME, TTS_MODE_SELFVOICED):
            self.mode = mode
            self._dirty = True

    def set_language(self, language: str, reset_voices: bool = False) -> None:
        """Set preferred language.

        Args:
            language: Language code (e.g., "en", "fr").
            reset_voices: If True, reset all voices to language defaults.
        """
        self.language = language
        self._dirty = True

        if reset_voices:
            self.reset_voices_to_language(language)

    def reset_voices_to_language(self, language: str | None = None) -> None:
        """Reset all voice settings to language-appropriate defaults.

        Args:
            language: Language code. If None, uses current language.
        """
        if language is None:
            language = self.language

        defaults = DEFAULT_VOICES_BY_LANG.get(language, DEFAULT_VOICES_EN)
        for category in VOICE_CATEGORIES:
            cat_defaults = defaults.get(category, DEFAULT_VOICES_EN["atc"])
            self.voices[category] = VoiceCategorySettings(
                voice_name=cat_defaults["voice_name"],
                engine=cat_defaults["engine"],
                rate=cat_defaults["rate"],
            )
        self._dirty = True
        logger.info("Reset voices to %s defaults", language)

    def load(self, path: Path | str | None = None) -> bool:
        """Load settings from file.

        Args:
            path: Optional path to settings file.
                 Defaults to ~/.airborne/settings.json.

        Returns:
            True if loaded successfully, False otherwise.
        """
        if path is not None:
            self._settings_path = Path(path)

        if not self._settings_path.exists():
            logger.info("No settings file found, using defaults")
            return False

        try:
            with open(self._settings_path, encoding="utf-8") as f:
                data = json.load(f)

            tts_data = data.get("tts", {})
            self.mode = tts_data.get("mode", TTS_MODE_REALTIME)
            self.language = tts_data.get("language", "en")

            voices_data = tts_data.get("voices", {})
            for category, voice_data in voices_data.items():
                if isinstance(voice_data, dict):
                    self.voices[category] = VoiceCategorySettings.from_dict(voice_data)

            # Ensure all categories have settings
            self.__post_init__()

            self._dirty = False
            logger.info("Loaded TTS settings from %s", self._settings_path)
            return True

        except Exception as e:
            logger.error("Failed to load settings: %s", e)
            return False

    def save(self, path: Path | str | None = None) -> bool:
        """Save settings to file.

        Args:
            path: Optional path to settings file.
                 Defaults to ~/.airborne/settings.json.

        Returns:
            True if saved successfully, False otherwise.
        """
        if path is not None:
            self._settings_path = Path(path)

        try:
            # Create directory if needed
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)

            # Load existing data to preserve non-TTS settings
            existing_data: dict[str, Any] = {}
            if self._settings_path.exists():
                with open(self._settings_path, encoding="utf-8") as f:
                    existing_data = json.load(f)

            # Update TTS section
            existing_data["tts"] = {
                "mode": self.mode,
                "language": self.language,
                "voices": {category: voice.to_dict() for category, voice in self.voices.items()},
            }

            # Write back
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2)

            self._dirty = False
            logger.info("Saved TTS settings to %s", self._settings_path)
            return True

        except Exception as e:
            logger.error("Failed to save settings: %s", e)
            return False

    @property
    def is_dirty(self) -> bool:
        """Check if settings have unsaved changes."""
        return self._dirty

    def reset_to_defaults(self) -> None:
        """Reset all settings to defaults."""
        self.mode = TTS_MODE_REALTIME
        self.language = "en"
        self.voices.clear()
        self.__post_init__()
        self._dirty = True

    def get_all_categories(self) -> list[str]:
        """Get list of all voice categories.

        Returns:
            List of category names.
        """
        return list(VOICE_CATEGORIES)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of settings.
        """
        return {
            "mode": self.mode,
            "language": self.language,
            "voices": {category: voice.to_dict() for category, voice in self.voices.items()},
        }


# Global singleton instance
_global_settings: TTSSettings | None = None


def get_tts_settings() -> TTSSettings:
    """Get the global TTS settings singleton.

    Loads settings from disk on first access.

    Returns:
        TTSSettings instance.
    """
    global _global_settings
    if _global_settings is None:
        _global_settings = TTSSettings()
        _global_settings.load()
    return _global_settings


def reset_tts_settings() -> None:
    """Reset the global TTS settings singleton.

    Forces reload on next access.
    """
    global _global_settings
    _global_settings = None

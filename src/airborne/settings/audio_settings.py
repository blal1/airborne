"""Audio settings management.

This module manages audio preferences including input device selection
and volume levels for different audio categories.

Settings are stored in ~/.airborne/settings.json.

Typical usage:
    from airborne.settings import get_audio_settings

    settings = get_audio_settings()
    settings.set_input_device(1, "MacBook Pro Microphone")
    settings.set_volume("master", 0.8)
    settings.save()
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Volume categories exposed in the audio settings menu
VOLUME_CATEGORIES = [
    "master",
    "music",
    "engine",
    "environment",
    "ui",
    "cockpit",
    "atc",
    "pilot",
    "cue",
]

# Default volumes (all at 100%)
DEFAULT_VOLUMES: dict[str, float] = {
    "master": 1.0,
    "music": 1.0,
    "engine": 1.0,
    "environment": 1.0,
    "ui": 1.0,
    "cockpit": 1.0,
    "atc": 1.0,
    "pilot": 1.0,
    "cue": 1.0,
}


@dataclass
class AudioSettings:
    """Audio settings manager with persistence.

    Manages audio input device selection and volume levels for all
    audio categories. Settings persist to ~/.airborne/settings.json.

    Attributes:
        input_device_index: Selected recording device index (0 = default).
        input_device_name: Human-readable device name for display.
        volumes: Dictionary of category -> volume level (0.0 to 1.0).
    """

    input_device_index: int = 0
    input_device_name: str = ""
    volumes: dict[str, float] = field(default_factory=dict)
    _settings_path: Path = field(
        default_factory=lambda: Path.home() / ".airborne" / "settings.json"
    )
    _dirty: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize default volumes for any missing categories."""
        for category in VOLUME_CATEGORIES:
            if category not in self.volumes:
                self.volumes[category] = DEFAULT_VOLUMES.get(category, 1.0)

    def get_volume(self, category: str) -> float:
        """Get volume for a category.

        Args:
            category: Volume category name (e.g., "master", "engine").

        Returns:
            Volume level from 0.0 to 1.0.
        """
        return self.volumes.get(category, 1.0)

    def set_volume(self, category: str, volume: float) -> None:
        """Set volume for a category.

        Args:
            category: Volume category name.
            volume: Volume level from 0.0 to 1.0.
        """
        # Clamp to valid range
        volume = max(0.0, min(1.0, volume))
        self.volumes[category] = volume
        self._dirty = True

    def set_input_device(self, index: int, name: str = "") -> None:
        """Set the audio input device.

        Args:
            index: Device index from FMOD.
            name: Human-readable device name.
        """
        self.input_device_index = index
        self.input_device_name = name
        self._dirty = True

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
            logger.info("No settings file found, using audio defaults")
            return False

        try:
            with open(self._settings_path, encoding="utf-8") as f:
                data = json.load(f)

            audio_data = data.get("audio", {})
            self.input_device_index = audio_data.get("input_device_index", 0)
            self.input_device_name = audio_data.get("input_device_name", "")

            volumes_data = audio_data.get("volumes", {})
            for category, volume in volumes_data.items():
                if isinstance(volume, (int, float)):
                    self.volumes[category] = float(volume)

            # Ensure all categories have settings
            self.__post_init__()

            self._dirty = False
            logger.info("Loaded audio settings from %s", self._settings_path)
            return True

        except Exception as e:
            logger.error("Failed to load audio settings: %s", e)
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

            # Load existing data to preserve other settings
            existing_data: dict[str, Any] = {}
            if self._settings_path.exists():
                with open(self._settings_path, encoding="utf-8") as f:
                    existing_data = json.load(f)

            # Update audio section
            existing_data["audio"] = {
                "input_device_index": self.input_device_index,
                "input_device_name": self.input_device_name,
                "volumes": self.volumes.copy(),
            }

            # Write back
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2)

            self._dirty = False
            logger.info("Saved audio settings to %s", self._settings_path)
            return True

        except Exception as e:
            logger.error("Failed to save audio settings: %s", e)
            return False

    @property
    def is_dirty(self) -> bool:
        """Check if settings have unsaved changes."""
        return self._dirty

    def reset_to_defaults(self) -> None:
        """Reset all settings to defaults."""
        self.input_device_index = 0
        self.input_device_name = ""
        self.volumes.clear()
        self.__post_init__()
        self._dirty = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of settings.
        """
        return {
            "input_device_index": self.input_device_index,
            "input_device_name": self.input_device_name,
            "volumes": self.volumes.copy(),
        }


# Global singleton instance
_global_settings: AudioSettings | None = None


def get_audio_settings() -> AudioSettings:
    """Get the global audio settings singleton.

    Loads settings from disk on first access.

    Returns:
        AudioSettings instance.
    """
    global _global_settings
    if _global_settings is None:
        _global_settings = AudioSettings()
        _global_settings.load()
    return _global_settings


def reset_audio_settings() -> None:
    """Reset the global audio settings singleton.

    Forces reload on next access.
    """
    global _global_settings
    _global_settings = None

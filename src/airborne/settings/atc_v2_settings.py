"""ATC V2 voice control settings management.

This module manages settings for the ATC V2 voice control system,
including ASR/NLU provider selection and microphone configuration.

Settings are stored in ~/.airborne/settings.json under the "atc_v2" key.

Typical usage:
    from airborne.settings import get_atc_v2_settings

    settings = get_atc_v2_settings()
    settings.enabled = True
    settings.save()
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Provider types
PROVIDER_LOCAL = "local"
PROVIDER_REMOTE = "remote"

# Default Whisper model for ASR
DEFAULT_WHISPER_MODEL = "base.en"

# Default Llama model (user must provide path)
DEFAULT_LLAMA_MODEL_PATH = ""


@dataclass
class ATCV2Settings:
    """ATC V2 voice control settings with persistence.

    Manages settings for voice-controlled ATC interaction including
    ASR provider, NLU provider, and microphone configuration.

    Settings are stored in ~/.airborne/settings.json alongside TTS settings.

    Attributes:
        enabled: Whether ATC V2 voice mode is enabled.
        ptt_key: Push-to-talk key name (pygame key constant name).
        input_device_index: Microphone device index (None for default).
        input_device_name: Microphone device name (for display).
        asr_provider: ASR provider type ("local" or "remote").
        nlu_provider: NLU provider type ("local" or "remote").
        whisper_model: Whisper model size for local ASR.
        llama_model_path: Path to Llama GGUF model for local NLU.
        remote_server_url: URL for remote ASR/NLU server (future).
    """

    enabled: bool = False
    ptt_key: str = "SPACE"
    input_device_index: int | None = None
    input_device_name: str = ""
    asr_provider: str = PROVIDER_LOCAL
    nlu_provider: str = PROVIDER_LOCAL
    whisper_model: str = DEFAULT_WHISPER_MODEL
    llama_model_path: str = DEFAULT_LLAMA_MODEL_PATH
    remote_server_url: str = ""
    _settings_path: Path = field(
        default_factory=lambda: Path.home() / ".airborne" / "settings.json"
    )
    _dirty: bool = field(default=False, repr=False)

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable ATC V2 voice mode.

        Args:
            enabled: True to enable, False to disable.
        """
        self.enabled = enabled
        self._dirty = True

    def set_ptt_key(self, key: str) -> None:
        """Set push-to-talk key.

        Args:
            key: Pygame key constant name (e.g., "SPACE", "LCTRL").
        """
        self.ptt_key = key
        self._dirty = True

    def set_input_device(self, index: int | None, name: str = "") -> None:
        """Set microphone input device.

        Args:
            index: Device index from FMOD, or None for default.
            name: Human-readable device name.
        """
        self.input_device_index = index
        self.input_device_name = name
        self._dirty = True

    def set_asr_provider(self, provider: str) -> None:
        """Set ASR provider type.

        Args:
            provider: "local" or "remote".
        """
        if provider in (PROVIDER_LOCAL, PROVIDER_REMOTE):
            self.asr_provider = provider
            self._dirty = True

    def set_nlu_provider(self, provider: str) -> None:
        """Set NLU provider type.

        Args:
            provider: "local" or "remote".
        """
        if provider in (PROVIDER_LOCAL, PROVIDER_REMOTE):
            self.nlu_provider = provider
            self._dirty = True

    def set_whisper_model(self, model: str) -> None:
        """Set Whisper model size for local ASR.

        Args:
            model: Model name (e.g., "tiny.en", "base.en", "small.en").
        """
        self.whisper_model = model
        self._dirty = True

    def set_llama_model_path(self, path: str) -> None:
        """Set path to Llama GGUF model for local NLU.

        Args:
            path: Absolute path to the GGUF model file.
        """
        self.llama_model_path = path
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
            logger.info("No settings file found, using ATC V2 defaults")
            return False

        try:
            with open(self._settings_path, encoding="utf-8") as f:
                data = json.load(f)

            v2_data = data.get("atc_v2", {})
            self.enabled = v2_data.get("enabled", False)
            self.ptt_key = v2_data.get("ptt_key", "SPACE")
            self.input_device_index = v2_data.get("input_device_index")
            self.input_device_name = v2_data.get("input_device_name", "")
            self.asr_provider = v2_data.get("asr_provider", PROVIDER_LOCAL)
            self.nlu_provider = v2_data.get("nlu_provider", PROVIDER_LOCAL)
            self.whisper_model = v2_data.get("whisper_model", DEFAULT_WHISPER_MODEL)
            self.llama_model_path = v2_data.get("llama_model_path", DEFAULT_LLAMA_MODEL_PATH)
            self.remote_server_url = v2_data.get("remote_server_url", "")

            self._dirty = False
            logger.info("Loaded ATC V2 settings from %s", self._settings_path)
            return True

        except Exception as e:
            logger.error("Failed to load ATC V2 settings: %s", e)
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

            # Update ATC V2 section
            existing_data["atc_v2"] = {
                "enabled": self.enabled,
                "ptt_key": self.ptt_key,
                "input_device_index": self.input_device_index,
                "input_device_name": self.input_device_name,
                "asr_provider": self.asr_provider,
                "nlu_provider": self.nlu_provider,
                "whisper_model": self.whisper_model,
                "llama_model_path": self.llama_model_path,
                "remote_server_url": self.remote_server_url,
            }

            # Write back
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2)

            self._dirty = False
            logger.info("Saved ATC V2 settings to %s", self._settings_path)
            return True

        except Exception as e:
            logger.error("Failed to save ATC V2 settings: %s", e)
            return False

    @property
    def is_dirty(self) -> bool:
        """Check if settings have unsaved changes."""
        return self._dirty

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of settings.
        """
        return {
            "enabled": self.enabled,
            "ptt_key": self.ptt_key,
            "input_device_index": self.input_device_index,
            "input_device_name": self.input_device_name,
            "asr_provider": self.asr_provider,
            "nlu_provider": self.nlu_provider,
            "whisper_model": self.whisper_model,
            "llama_model_path": self.llama_model_path,
            "remote_server_url": self.remote_server_url,
        }


# Global singleton instance
_global_settings: ATCV2Settings | None = None


def get_atc_v2_settings() -> ATCV2Settings:
    """Get the global ATC V2 settings singleton.

    Loads settings from disk on first access.

    Returns:
        ATCV2Settings instance.
    """
    global _global_settings
    if _global_settings is None:
        _global_settings = ATCV2Settings()
        _global_settings.load()
    return _global_settings


def reset_atc_v2_settings() -> None:
    """Reset the global ATC V2 settings singleton.

    Forces reload on next access.
    """
    global _global_settings
    _global_settings = None

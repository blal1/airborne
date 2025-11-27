"""TTS Manager with support for multiple backends.

This module provides a unified TTS interface that supports two backends:
1. "self-voiced" - Pre-generated audio chunks (default, uses phraseology system)
2. "system" - Real-time pyttsx3 synthesis (fluent speech, cross-platform)

The backend can be selected via:
- CLI argument: --tts=system or --tts=self-voiced
- Config file: tts.default_backend in speech.yaml

Typical usage:
    from airborne.audio.tts import TTSManager

    # Create manager with config
    tts = TTSManager(audio_engine, speech_config, backend="system")

    # Speak a message (uses voice from config)
    tts.speak("Tower, Cessna 123AB ready for departure", voice="pilot")

    # Or with ATC phraseology (self-voiced mode only)
    tts.speak_phrase(phrase_builder.build_callsign_phrase("N123AB"))
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from airborne.audio.realtime_tts import RealtimeTTS
from airborne.core.resource_path import get_resource_path

logger = logging.getLogger(__name__)


class TTSBackend(Enum):
    """TTS backend types."""

    SELF_VOICED = "self-voiced"  # Pre-generated audio chunks
    SYSTEM = "system"  # pyttsx3 real-time synthesis


@dataclass
class VoiceConfig:
    """Voice configuration for TTS.

    Attributes:
        name: Voice identifier (pilot, cockpit, tower, etc.)
        description: Human-readable description
        output_dir: Directory for pre-generated audio (self-voiced mode)
        pyttsx3_voice: Voice name for pyttsx3 (system mode)
        rate: Speech rate in words per minute
        volume: Volume level (0.0 to 1.0)
    """

    name: str
    description: str
    output_dir: str
    pyttsx3_voice: str | None = None
    rate: int = 180
    volume: float = 1.0


class TTSManager:
    """Unified TTS manager supporting multiple backends.

    Provides a single interface for text-to-speech that can use either
    pre-generated audio chunks (self-voiced) or real-time synthesis (system).

    The self-voiced backend uses the phraseology system to assemble messages
    from pre-recorded audio chunks, providing authentic ATC-style communication.

    The system backend uses pyttsx3 for real-time synthesis, producing more
    fluent speech but with less control over individual word pronunciation.

    Attributes:
        backend: Current TTS backend (self-voiced or system)
        voices: Dictionary of voice configurations

    Examples:
        >>> tts = TTSManager(engine, config)
        >>> tts.speak("Cleared for takeoff runway 31", voice="tower")
    """

    def __init__(
        self,
        audio_engine: Any,
        config_path: Path | str | None = None,
        backend: str | TTSBackend | None = None,
        speech_dir: Path | str | None = None,
    ) -> None:
        """Initialize TTS manager.

        Args:
            audio_engine: FMOD audio engine instance
            config_path: Path to speech.yaml config file
            backend: TTS backend to use (overrides config default)
            speech_dir: Base directory for speech audio files
        """
        self._audio_engine = audio_engine
        self._voices: dict[str, VoiceConfig] = {}
        self._realtime_tts: dict[str, RealtimeTTS] = {}  # Per-voice TTS instances
        self._speech_dir = Path(speech_dir) if speech_dir else get_resource_path("data/speech/en")
        self._config: dict[str, Any] = {}

        # Load configuration
        if config_path:
            self._load_config(Path(config_path))
        else:
            # Try default config location
            default_config = get_resource_path("config/speech.yaml")
            if default_config.exists():
                self._load_config(default_config)

        # Determine backend
        if backend:
            if isinstance(backend, TTSBackend):
                self._backend = backend
            else:
                self._backend = TTSBackend(backend)
        else:
            # Use config default or fall back to self-voiced
            default = self._config.get("tts", {}).get("default_backend", "self-voiced")
            self._backend = TTSBackend(default)

        logger.info(
            "TTSManager initialized: backend=%s, voices=%d",
            self._backend.value,
            len(self._voices),
        )

    def _load_config(self, config_path: Path) -> None:
        """Load speech configuration from YAML file.

        Args:
            config_path: Path to speech.yaml
        """
        if not config_path.exists():
            logger.warning("Speech config not found: %s", config_path)
            return

        try:
            with open(config_path, encoding="utf-8") as f:
                self._config = yaml.safe_load(f)

            # Parse voice configurations
            voices_config = self._config.get("voices", {})
            for name, voice_data in voices_config.items():
                pyttsx3_config = voice_data.get("pyttsx3", {})

                self._voices[name] = VoiceConfig(
                    name=name,
                    description=voice_data.get("description", ""),
                    output_dir=voice_data.get("output_dir", name),
                    pyttsx3_voice=pyttsx3_config.get("voice_name"),
                    rate=pyttsx3_config.get("rate", voice_data.get("rate", 180)),
                    volume=pyttsx3_config.get("volume", voice_data.get("volume", 1.0)),
                )

            logger.info("Loaded %d voice configurations from %s", len(self._voices), config_path)

        except Exception as e:
            logger.error("Failed to load speech config: %s", e)

    def set_backend(self, backend: str | TTSBackend) -> None:
        """Change the TTS backend.

        Args:
            backend: New backend to use
        """
        if isinstance(backend, str):
            backend = TTSBackend(backend)
        self._backend = backend
        logger.info("TTS backend changed to: %s", self._backend.value)

    @property
    def backend(self) -> TTSBackend:
        """Get current TTS backend."""
        return self._backend

    def get_voice(self, voice_name: str) -> VoiceConfig | None:
        """Get voice configuration by name.

        Args:
            voice_name: Voice identifier (pilot, tower, etc.)

        Returns:
            VoiceConfig or None if not found
        """
        return self._voices.get(voice_name)

    def speak(
        self,
        text: str,
        voice: str = "cockpit",
        volume: float | None = None,
        blocking: bool = True,
    ) -> int | None:
        """Speak text using the configured backend.

        For self-voiced backend, this will try to assemble the message from
        pre-generated chunks. If chunks aren't available, falls back to
        system TTS.

        For system backend, generates speech in real-time using pyttsx3.

        Args:
            text: Text to speak
            voice: Voice name from config (pilot, tower, cockpit, etc.)
            volume: Override volume (0.0-1.0), or None to use voice config
            blocking: If True, wait for speech to complete

        Returns:
            Source ID of the played sound, or None if failed
        """
        voice_config = self._voices.get(voice)
        if not voice_config:
            logger.warning("Unknown voice '%s', using default", voice)
            voice_config = VoiceConfig(name=voice, description="", output_dir="")

        actual_volume = volume if volume is not None else voice_config.volume

        if self._backend == TTSBackend.SELF_VOICED:
            return self._speak_self_voiced(text, voice_config, actual_volume, blocking)
        else:
            return self._speak_system(text, voice_config, actual_volume, blocking)

    def _speak_self_voiced(
        self,
        text: str,
        voice_config: VoiceConfig,
        volume: float,
        blocking: bool,
    ) -> int | None:
        """Speak using pre-generated audio chunks.

        Tries to find matching audio files for the text. If not found,
        falls back to system TTS.

        Args:
            text: Text to speak
            voice_config: Voice configuration
            volume: Volume level
            blocking: Wait for completion

        Returns:
            Source ID or None
        """
        # Look for a pre-generated file matching this text
        # For now, we use a simple hash-based lookup
        # In practice, the phraseology system would provide audio file paths
        audio_dir = self._speech_dir / voice_config.output_dir

        # Try to find existing audio file
        # This is a simplified lookup - the full implementation would use
        # the phraseology system's word-by-word chunk assembly
        import hashlib

        text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        audio_file = audio_dir / f"{text_hash}.ogg"

        if audio_file.exists():
            return self._play_audio_file(audio_file, volume, blocking)

        # Fall back to system TTS if no pre-generated audio
        logger.debug("No pre-generated audio for '%s', using system TTS", text[:30])
        return self._speak_system(text, voice_config, volume, blocking)

    def _speak_system(
        self,
        text: str,
        voice_config: VoiceConfig,
        volume: float,
        blocking: bool,
    ) -> int | None:
        """Speak using pyttsx3 real-time synthesis.

        Args:
            text: Text to speak
            voice_config: Voice configuration
            volume: Volume level
            blocking: Wait for completion

        Returns:
            Source ID or None
        """
        # Get or create RealtimeTTS instance for this voice
        tts = self._get_realtime_tts(voice_config)

        # Generate audio bytes
        result = tts.generate_audio_bytes(text)
        if not result:
            logger.error("System TTS failed for: %s", text[:30])
            return None

        audio_bytes, audio_format = result

        # Load and play through FMOD
        try:
            sound = self._audio_engine.load_sound_from_bytes(
                audio_bytes, f"tts_{voice_config.name}"
            )
            source_id: int | None = self._audio_engine.play_2d(sound, volume=volume, loop=False)

            if blocking and source_id:
                self._wait_for_playback(source_id)

            return source_id

        except Exception as e:
            logger.error("Failed to play TTS audio: %s", e)
            return None

    def _get_realtime_tts(self, voice_config: VoiceConfig) -> RealtimeTTS:
        """Get or create RealtimeTTS instance for a voice.

        Args:
            voice_config: Voice configuration

        Returns:
            RealtimeTTS instance configured for the voice
        """
        if voice_config.name not in self._realtime_tts:
            self._realtime_tts[voice_config.name] = RealtimeTTS(
                rate=voice_config.rate,
                voice_name=voice_config.pyttsx3_voice,
                cache_enabled=True,
            )
        return self._realtime_tts[voice_config.name]

    def _play_audio_file(
        self,
        audio_path: Path,
        volume: float,
        blocking: bool,
    ) -> int | None:
        """Play an audio file through the audio engine.

        Args:
            audio_path: Path to audio file
            volume: Volume level
            blocking: Wait for completion

        Returns:
            Source ID or None
        """
        try:
            sound = self._audio_engine.load_sound(str(audio_path))
            source_id: int | None = self._audio_engine.play_2d(sound, volume=volume, loop=False)

            if blocking and source_id:
                self._wait_for_playback(source_id)

            return source_id

        except Exception as e:
            logger.error("Failed to play audio file %s: %s", audio_path, e)
            return None

    def _wait_for_playback(self, source_id: int) -> None:
        """Wait for audio playback to complete.

        Args:
            source_id: Source ID to wait for
        """
        import time

        try:
            channel = self._audio_engine._channels.get(source_id)
            if channel:
                while channel.is_playing:
                    self._audio_engine._system.update()
                    time.sleep(0.016)
        except Exception as e:
            logger.debug("Error waiting for playback: %s", e)

    def speak_phrase(
        self,
        phrase: dict[str, Any],
        voice: str = "tower",
        volume: float | None = None,
        blocking: bool = True,
    ) -> int | None:
        """Speak a phrase built by the phraseology system.

        This is the preferred method for ATC communications as it uses
        the chunk-based system for authentic pronunciation.

        Args:
            phrase: Phrase dict from PhraseBuilder (has 'words' and 'audio_files')
            voice: Voice name for fallback text-to-speech
            volume: Override volume
            blocking: Wait for completion

        Returns:
            Source ID of last played chunk, or None
        """
        voice_config = self._voices.get(voice)
        if not voice_config:
            voice_config = VoiceConfig(name=voice, description="", output_dir="")

        actual_volume = volume if volume is not None else voice_config.volume

        if self._backend == TTSBackend.SELF_VOICED:
            # Play audio chunks in sequence
            return self._speak_phrase_chunks(phrase, actual_volume, blocking)
        else:
            # System mode: synthesize the full text
            text = phrase.get("text", " ".join(phrase.get("words", [])))
            return self._speak_system(text, voice_config, actual_volume, blocking)

    def _speak_phrase_chunks(
        self,
        phrase: dict[str, Any],
        volume: float,
        blocking: bool,
    ) -> int | None:
        """Play phrase audio chunks in sequence.

        Args:
            phrase: Phrase dict with 'audio_files' list
            volume: Volume level
            blocking: Wait for each chunk

        Returns:
            Source ID of last chunk, or None
        """
        audio_files = phrase.get("audio_files", [])
        if not audio_files:
            # Fall back to text
            text = phrase.get("text", "")
            if text:
                return self.speak(text, volume=volume, blocking=blocking)
            return None

        source_id = None
        for audio_file in audio_files:
            audio_path = Path(audio_file)
            if not audio_path.is_absolute():
                audio_path = self._speech_dir / audio_file

            if audio_path.exists():
                source_id = self._play_audio_file(audio_path, volume, blocking=True)
            else:
                logger.warning("Audio chunk not found: %s", audio_path)

        return source_id

    def speak_message(
        self,
        message_key: str,
        voice: str | None = None,
        volume: float | None = None,
        blocking: bool = True,
    ) -> int | None:
        """Speak a predefined message from config.

        Args:
            message_key: Message key from speech.yaml (e.g., "MSG_STARTUP")
            voice: Override voice (uses message's default if None)
            volume: Override volume
            blocking: Wait for completion

        Returns:
            Source ID or None
        """
        messages = self._config.get("messages", {})
        message_data = messages.get(message_key)

        if not message_data:
            logger.warning("Unknown message key: %s", message_key)
            return None

        text = message_data.get("text", "")
        msg_voice = voice or message_data.get("voice", "cockpit")

        return self.speak(text, voice=msg_voice, volume=volume, blocking=blocking)

    def get_available_voices(self) -> list[str]:
        """Get list of available voice names.

        Returns:
            List of voice identifiers
        """
        return list(self._voices.keys())

    def cleanup(self) -> None:
        """Clean up TTS resources."""
        for tts in self._realtime_tts.values():
            tts.cleanup()
        self._realtime_tts.clear()
        logger.info("TTSManager cleanup complete")

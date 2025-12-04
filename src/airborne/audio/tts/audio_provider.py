"""TTS provider implementation using realtime system TTS.

This module provides TTS via the shared TTSService facade,
which manages a single asyncio event loop and TTSServiceClient.

Typical usage example:
    from airborne.audio.tts.audio_provider import AudioSpeechProvider
    from airborne.core.i18n import t

    tts = AudioSpeechProvider()
    tts.initialize({"language": "en", "audio_engine": engine, "tts_service": service})
    tts.speak(t("cockpit.altitude_readout", value=3500))
"""

import threading
from collections import deque
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

try:
    import pyfmodex
    from pyfmodex.enums import CHANNELCONTROL_CALLBACK_TYPE
except ImportError:
    pyfmodex = None
    CHANNELCONTROL_CALLBACK_TYPE = None

from airborne.audio.realtime_tts import RealtimeTTS
from airborne.audio.tts.base import ITTSProvider, TTSPriority, TTSState
from airborne.audio.tts_service import TTSPriority as ServicePriority
from airborne.core.logging_system import get_logger

if TYPE_CHECKING:
    from airborne.audio.tts_service import TTSService

logger = get_logger(__name__)


class SpeechItem:
    """Item in the speech queue."""

    def __init__(
        self,
        text: str,
        priority: TTSPriority,
        callback: Callable[[], None] | None = None,
    ) -> None:
        """Initialize speech item.

        Args:
            text: Text to speak (will be mapped to audio file).
            priority: Priority level.
            callback: Optional completion callback.
        """
        self.text = text
        self.priority = priority
        self.callback = callback


class AudioSpeechProvider(ITTSProvider):
    """Realtime TTS provider using system text-to-speech.

    Uses pyttsx3 via TTSService to generate speech in realtime.
    Text is passed directly to speak() - use t() for translations.

    Examples:
        >>> from airborne.core.i18n import t
        >>> tts = AudioSpeechProvider()
        >>> tts.initialize({"language": "en", "audio_engine": engine, "tts_service": service})
        >>> tts.speak(t("system.startup"))
        >>> tts.shutdown()
    """

    def __init__(self) -> None:
        """Initialize the provider (not started yet)."""
        self._initialized = False
        self._state = TTSState.IDLE
        self._queue: deque[SpeechItem] = deque()
        self._current_item: SpeechItem | None = None
        self._lock = threading.Lock()
        self._stop_requested = False
        self._shutdown_requested = False
        self._language = "en"

        # Audio engine reference (will be injected)
        self._audio_engine: Any = None
        self._current_source_id: int | None = None

        # Sequential playback queue
        self._playback_queue: deque[Any] = deque()  # Preloaded sound objects
        self._playing = False
        self._callback_lock = threading.Lock()  # Protect callback access

        # Shared TTSService (injected from main.py)
        self._tts_service: TTSService | None = None

        # RealtimeTTS instances for ATC/radio speech
        self._realtime_tts_cache: dict[str, RealtimeTTS] = {}

    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize audio speech provider.

        Args:
            config: Configuration with keys:
                - language: Language code (default: "en")
                - audio_engine: Reference to audio engine (required)
                - tts_service: Shared TTSService instance (required)
        """
        if self._initialized:
            logger.warning("AudioSpeechProvider already initialized")
            return

        self._language = config.get("language", "en")
        self._audio_engine = config.get("audio_engine")

        if not self._audio_engine:
            logger.error("No audio engine provided to AudioSpeechProvider")
            return

        # Get shared TTSService from config
        self._tts_service = config.get("tts_service")
        if not self._tts_service:
            logger.warning("No TTSService provided, TTS will be disabled")
        elif not self._tts_service.is_running:
            logger.warning("TTSService not running, TTS will be disabled")
        else:
            logger.info("Using shared TTSService for TTS")

        self._initialized = True
        logger.info(
            "AudioSpeechProvider initialized: language=%s",
            self._language,
        )

    def _get_realtime_tts(self, voice_category: str = "cockpit") -> RealtimeTTS | None:
        """Get a RealtimeTTS instance for generating audio bytes.

        This method is used by ATCAudioManager and RadioPlugin for generating
        dynamic ATC/radio speech with radio effects.

        Args:
            voice_category: Voice category (cockpit, tower, pilot, atis, etc.).

        Returns:
            RealtimeTTS instance configured for the voice, or None if not available.
        """
        if not self._initialized:
            return None

        # Get voice settings for this category
        from airborne.settings import get_tts_settings

        tts_settings = get_tts_settings()
        voice_settings = tts_settings.get_voice(voice_category)
        voice_name = voice_settings.voice_name
        speech_rate = voice_settings.rate

        # Cache key based on voice settings
        cache_key = f"{voice_category}_{voice_name}_{speech_rate}"

        if cache_key not in self._realtime_tts_cache:
            self._realtime_tts_cache[cache_key] = RealtimeTTS(
                rate=speech_rate,
                voice_name=voice_name,
            )
            logger.info(
                f"Created RealtimeTTS for {voice_category}: voice={voice_name}, rate={speech_rate}"
            )

        return self._realtime_tts_cache[cache_key]

    def shutdown(self) -> None:
        """Shutdown audio speech provider."""
        if not self._initialized:
            return

        self.stop()
        self.clear_queue()

        # Clean up RealtimeTTS cache
        for tts in self._realtime_tts_cache.values():
            tts.cleanup()
        self._realtime_tts_cache.clear()

        # Note: TTSService lifecycle is managed by main.py, not here
        self._tts_service = None

        self._initialized = False
        logger.info("AudioSpeechProvider shutdown")

    def speak(
        self,
        text: str,
        priority: TTSPriority = TTSPriority.NORMAL,
        interrupt: bool = False,
        callback: Callable[[], None] | None = None,
    ) -> None:
        """Speak text using TTS.

        Args:
            text: Text to speak.
            priority: Priority level.
            interrupt: If True, stop current speech.
            callback: Optional callback when done.
        """
        if not self._initialized:
            return

        if not text or not text.strip():
            return

        # Stop current speech if interrupt or critical
        if interrupt or priority == TTSPriority.CRITICAL:
            self.stop()

        self._speak_system(text, priority, interrupt, callback)

    def _speak_system(
        self,
        text: str,
        priority: TTSPriority,
        interrupt: bool,
        callback: Callable[[], None] | None = None,
        voice_category: str = "cockpit",
    ) -> None:
        """Speak text using system TTS via shared TTSService.

        Args:
            text: Text to speak (should already be translated).
            priority: Priority level.
            interrupt: If True, stop current speech.
            callback: Optional callback when done.
            voice_category: Voice category (cockpit, tower, etc.).
        """
        if not self._tts_service or not self._tts_service.is_running:
            logger.warning("TTSService not available")
            return

        # Get current voice settings from user preferences
        from airborne.settings import get_tts_settings

        tts_settings = get_tts_settings()
        current_language = tts_settings.language
        voice_settings = tts_settings.get_voice(voice_category)
        platform_voice_name = voice_settings.voice_name
        speech_rate = voice_settings.rate

        logger.info(
            f"TTS speaking: '{text}' (voice={voice_category}, "
            f"platform_voice={platform_voice_name}, lang={current_language})"
        )

        # Map local priority to service priority
        service_priority = ServicePriority.NORMAL
        if priority == TTSPriority.CRITICAL:
            service_priority = ServicePriority.CRITICAL
        elif priority == TTSPriority.HIGH:
            service_priority = ServicePriority.HIGH
        elif priority == TTSPriority.LOW:
            service_priority = ServicePriority.LOW

        # Queue via TTSService with callback for audio playback
        def on_audio_ready(audio_bytes: bytes) -> None:
            """Handle audio when ready - queue for playback."""
            try:
                sound = self._audio_engine.load_sound_from_bytes(
                    audio_bytes, f"tts_{voice_category}"
                )
                if sound:
                    self._playback_queue.append(sound)
                    self._state = TTSState.SPEAKING
                    if not self._playing:
                        self._play_next_in_sequence()
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(f"Error loading TTS audio: {e}")

        self._tts_service.speak(
            text=text,
            voice=voice_category,
            priority=service_priority,
            interrupt=interrupt,
            on_audio=on_audio_ready,
            voice_name=platform_voice_name,
            rate=speech_rate,
            language=current_language,
        )

    def set_context(self, context: str) -> None:
        """Set the flight context for TTS pre-generation prioritization.

        Tells the shared TTSService what context the sim is in so it can
        prioritize pre-generating the most likely needed TTS items.

        Args:
            context: Flight context ("menu", "ground", "airborne").
        """
        if not self._tts_service or not self._tts_service.is_running:
            logger.warning("TTSService not available for set_context")
            return

        # Delegate to shared TTSService
        self._tts_service.set_context(context, {})
        logger.info(f"Sent context change to TTSService: {context}")

    def speak_text(
        self,
        text: str,
        voice: str = "tower",
        priority: TTSPriority = TTSPriority.NORMAL,
        interrupt: bool = False,
        callback: Callable[[], None] | None = None,
    ) -> None:
        """Speak raw text directly using TTS with a specific voice.

        Args:
            text: Text to speak.
            voice: Voice category (tower, cockpit, atis, etc.).
            priority: Priority level.
            interrupt: If True, stop current speech.
            callback: Optional callback when done.
        """
        if not self._initialized or not text or not text.strip():
            return

        if interrupt or priority == TTSPriority.CRITICAL:
            self.stop()

        self._speak_system(text, priority, interrupt, callback, voice_category=voice)

    def stop(self) -> None:
        """Stop current speech immediately."""
        if not self._initialized:
            return

        self._stop_requested = True
        if self._current_source_id is not None and self._audio_engine:
            try:
                self._audio_engine.stop_source(self._current_source_id)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(f"Error stopping speech: {e}")
        self._state = TTSState.IDLE
        self._current_source_id = None
        self._playing = False
        self._playback_queue.clear()

        logger.debug("Stopped speech")

    def pause(self) -> None:
        """Pause current speech (not implemented for audio files)."""
        self.stop()
        self._state = TTSState.PAUSED

    def resume(self) -> None:
        """Resume speech (not implemented for audio files)."""
        self._state = TTSState.IDLE

    def is_speaking(self) -> bool:
        """Check if currently speaking.

        Returns:
            True if speaking.
        """
        with self._lock:
            return self._state == TTSState.SPEAKING

    def get_state(self) -> TTSState:
        """Get current TTS state.

        Returns:
            Current state.
        """
        with self._lock:
            return self._state

    def set_rate(self, rate: int) -> None:
        """Set speech rate (not applicable for pre-recorded audio).

        Args:
            rate: Words per minute (ignored).
        """
        logger.debug("set_rate not applicable for audio files")

    def set_volume(self, volume: float) -> None:
        """Set speech volume (not applicable for pre-recorded audio).

        Args:
            volume: Volume 0.0 to 1.0 (ignored).
        """
        logger.debug("set_volume not applicable for audio files")

    def set_voice(self, voice_id: str) -> None:
        """Set voice by ID (not applicable for pre-recorded audio).

        Args:
            voice_id: Voice identifier (ignored).
        """
        logger.debug("set_voice not applicable for audio files")

    def get_voices(self) -> list[dict[str, Any]]:
        """Get available voices.

        Returns:
            Empty list (pre-recorded audio).
        """
        return []

    def _on_sound_end(self, channelcontrol, controltype, callbacktype, data1, data2) -> None:
        """Callback when a sound finishes - immediately play next in sequence.

        This is called by FMOD's callback system when a channel stops.
        """
        try:
            with self._callback_lock:
                logger.debug("Sound finished via callback, playing next")
                self._playing = False
                self._current_source_id = None
                self._play_next_in_sequence()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Error in sound end callback: {e}")

    def _play_next_in_sequence(self) -> None:
        """Play the next sound in the sequence (if any).

        Called either initially or from the callback when a sound finishes.
        """
        # Check state and pop sound from queue within lock
        with self._callback_lock:
            if not self._playback_queue:
                self._playing = False
                self._state = TTSState.IDLE
                logger.info("TTS playback complete")
                return

            if self._playing:
                return

            # Mark as playing before releasing lock
            self._playing = True
            sound = self._playback_queue.popleft()

        # Play sound OUTSIDE the lock to avoid blocking update()
        try:
            source_id = self._audio_engine.play_2d(
                sound,
                volume=1.0,
                pitch=1.0,
                loop=False,
            )
            self._current_source_id = source_id
            logger.info(
                f"TTS playing sound (source_id={source_id}, {len(self._playback_queue)} remaining)"
            )

            # Callback setup removed - using polling in update() instead
            # FMOD callbacks are complex and fallback polling works fine

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Error playing speech sound: {e}")
            self._playing = False
            # Try next sound
            if self._playback_queue:
                self._play_next_in_sequence()

    def update(self) -> None:
        """Update sequential playback - call every frame.

        Uses polling to detect when sounds finish and trigger the next in sequence.
        Note: TTS callbacks are invoked by TTSService.update() in the main loop,
        which then queues sounds for playback here.
        """
        if not self._initialized or not self._audio_engine:
            return

        # Polling to detect when sounds finish
        if self._playing and self._current_source_id is not None:
            try:
                if hasattr(self._audio_engine, "_channels"):
                    channel = self._audio_engine._channels.get(self._current_source_id)
                    if channel:
                        try:
                            if not channel.is_playing:
                                # Sound finished - trigger next
                                logger.info("TTS sound finished")
                                self._playing = False
                                self._current_source_id = None
                                self._play_next_in_sequence()
                        except Exception as e:  # pylint: disable=broad-exception-caught
                            logger.error(f"Error checking channel.is_playing: {e}")
                    else:
                        # Channel not found means it was removed after finishing
                        logger.info("TTS sound finished")
                        self._playing = False
                        self._current_source_id = None
                        self._play_next_in_sequence()
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(f"Error in update() polling: {e}")

    def clear_queue(self) -> None:
        """Clear the speech queue."""
        with self._lock:
            self._queue.clear()
        logger.debug("Cleared speech queue")

    def get_queue_length(self) -> int:
        """Get queue length.

        Returns:
            Number of queued items.
        """
        with self._lock:
            return len(self._queue)

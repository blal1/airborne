"""Audio file-based TTS provider implementation with optional system TTS fallback.

This module provides a TTS implementation that can use either:
1. Pre-recorded audio files (self-voiced mode, default)
2. Real-time system TTS synthesis via TTS Cache Service (system mode)

The mode can be configured via:
- CLI argument: --tts=system or --tts=self-voiced
- Config: tts_mode in initialization config

In system mode, TTS generation is handled by the TTS Cache Service subprocess,
which runs pyttsx3 in its main thread to avoid macOS threading issues.

Messages are mapped to audio files using YAML configuration files in config/speech.yaml.

Typical usage example:
    from airborne.audio.tts.audio_provider import AudioSpeechProvider
    from airborne.audio.tts.speech_messages import MSG_STARTUP

    tts = AudioSpeechProvider()
    tts.initialize({"language": "en", "audio_engine": engine, "tts_mode": "system"})
    tts.speak(MSG_STARTUP)
"""

import asyncio
import contextlib
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

try:
    import pyfmodex
    from pyfmodex.enums import CHANNELCONTROL_CALLBACK_TYPE
except ImportError:
    pyfmodex = None
    CHANNELCONTROL_CALLBACK_TYPE = None

from airborne.audio.realtime_tts import RealtimeTTS
from airborne.audio.tts.base import ITTSProvider, TTSPriority, TTSState
from airborne.core.logging_system import get_logger

if TYPE_CHECKING:
    from airborne.tts_cache_service import TTSServiceClient

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
    """Audio file-based TTS provider.

    Uses pre-recorded audio files (OGG format) with YAML-based configuration.
    Messages are identified by keys (e.g., MSG_STARTUP) and mapped to audio files
    via config/speech_{language}.yaml.

    Examples:
        >>> from airborne.audio.tts.speech_messages import MSG_STARTUP
        >>> tts = AudioSpeechProvider()
        >>> tts.initialize({"language": "en", "audio_engine": engine})
        >>> tts.speak(MSG_STARTUP)
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
        self._speech_dir = Path("data/speech")
        self._config_dir = Path("config")
        self._language = "en"
        self._file_extension = "wav"
        self._message_map: dict[str, dict[str, str]] = {}  # key -> {text, voice}
        self._voice_dirs: dict[str, Path] = {}  # voice -> directory path
        self._voice_configs: dict[str, dict[str, Any]] = {}  # voice -> full config

        # Audio engine reference (will be injected)
        self._audio_engine: Any = None
        self._current_source_id: int | None = None

        # Sequential playback queue
        self._playback_queue: deque[Any] = deque()  # Preloaded sound objects
        self._playing = False
        self._callback_lock = threading.Lock()  # Protect callback access

        # System TTS mode (pyttsx3)
        self._tts_mode: str = "self-voiced"  # "self-voiced" or "system"
        self._realtime_tts: dict[str, RealtimeTTS] = {}  # Per-voice TTS instances

        # TTS Cache Service client (for system mode)
        self._tts_service_client: TTSServiceClient | None = None
        self._tts_service_loop: asyncio.AbstractEventLoop | None = None
        self._tts_service_thread: threading.Thread | None = None
        self._tts_request_queue: deque[
            tuple[str, str, int, str | None, Callable[[bytes | None], None] | None]
        ] = deque()
        self._tts_result_queue: deque[tuple[bytes | None, Any]] = deque()  # (audio, sound)

    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize audio speech provider.

        Args:
            config: Configuration with keys:
                - language: Language code (default: "en")
                - speech_dir: Path to speech files directory (default: "data/speech")
                - config_dir: Path to config directory (default: "config")
                - audio_engine: Reference to audio engine (required)
                - tts_mode: "self-voiced" (pre-recorded) or "system" (pyttsx3)
        """
        if self._initialized:
            logger.warning("AudioSpeechProvider already initialized")
            return

        self._language = config.get("language", "en")
        speech_dir = config.get("speech_dir", "data/speech")
        self._config_dir = Path(config.get("config_dir", "config"))
        self._speech_dir = Path(speech_dir) / self._language
        self._audio_engine = config.get("audio_engine")
        self._tts_mode = config.get("tts_mode", "self-voiced")

        if not self._audio_engine:
            logger.error("No audio engine provided to AudioSpeechProvider")
            return

        # Load unified speech configuration YAML
        config_file = self._config_dir / "speech.yaml"
        if not config_file.exists():
            # Fall back to old format
            config_file = self._config_dir / f"speech_{self._language}.yaml"
            if not config_file.exists():
                logger.error(f"Speech config not found: {config_file}")
                return
            # Load old format
            try:
                with open(config_file, encoding="utf-8") as f:
                    speech_config = yaml.safe_load(f)
                self._file_extension = speech_config.get("file_extension", "wav")
                # Convert old format to new format
                old_messages = speech_config.get("messages", {})
                self._message_map = {key: {"text": key, "voice": "cockpit"} for key in old_messages}
                self._voice_dirs = {"cockpit": self._speech_dir}
                logger.info("Loaded %d speech messages (old format)", len(self._message_map))
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(f"Error loading speech config: {e}")
                return
        else:
            # Load new unified format
            try:
                with open(config_file, encoding="utf-8") as f:
                    speech_config = yaml.safe_load(f)

                # Build voice directory map and voice configs
                voices = speech_config.get("voices", {})
                for voice_name, voice_config in voices.items():
                    output_dir = voice_config.get("output_dir", voice_name)
                    self._voice_dirs[voice_name] = self._speech_dir / output_dir
                    self._voice_configs[voice_name] = voice_config

                # Load messages
                self._message_map = speech_config.get("messages", {})
                self._file_extension = "wav"  # New format uses WAV to avoid MP3 decoder latency

                logger.info(
                    "Loaded %d speech messages from %s (%d voices)",
                    len(self._message_map),
                    config_file,
                    len(self._voice_dirs),
                )
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(f"Error loading speech config: {e}")
                return

        # Create speech directory if it doesn't exist
        self._speech_dir.mkdir(parents=True, exist_ok=True)

        # Initialize TTS Cache Service client for system mode
        if self._tts_mode == "system":
            self._start_tts_service()

        self._initialized = True
        logger.info(
            "AudioSpeechProvider initialized: language=%s, dir=%s, format=%s, mode=%s",
            self._language,
            self._speech_dir,
            self._file_extension,
            self._tts_mode,
        )

    def shutdown(self) -> None:
        """Shutdown audio speech provider."""
        if not self._initialized:
            return

        self.stop()
        self.clear_queue()

        # Stop TTS Cache Service client
        self._stop_tts_service()

        self._initialized = False
        logger.info("AudioSpeechProvider shutdown")

    def speak(
        self,
        message_key: str | list[str],
        priority: TTSPriority = TTSPriority.NORMAL,
        interrupt: bool = False,
        callback: Callable[[], None] | None = None,
    ) -> None:
        """Speak message by playing corresponding audio file(s).

        Args:
            message_key: Message key or list of keys to play in sequence
                        (e.g., MSG_STARTUP or ["MSG_DIGIT_1", "MSG_DIGIT_2", "MSG_DIGIT_0"]).
            priority: Priority level.
            interrupt: If True, stop current speech.
            callback: Optional callback when done.
        """
        if not self._initialized:
            return

        # Convert single key to list
        if isinstance(message_key, str):
            if not message_key.strip():
                return
            message_keys = [message_key]
        else:
            message_keys = message_key

        if not message_keys:
            return

        # Stop current speech if interrupt or critical
        if interrupt or priority == TTSPriority.CRITICAL:
            self.stop()

        # Use system TTS mode (pyttsx3) if configured
        if self._tts_mode == "system":
            self._speak_system(message_keys, priority, interrupt, callback)
            return

        # Resolve all file paths and preload sounds
        sound_objects = []
        for key in message_keys:
            message_config = self._message_map.get(key)

            # If not in config, try to find file directly in voice directories
            if not message_config:
                found = False
                # Check if key specifies voice directory (e.g., "cockpit/number_42_autogen")
                if "/" in key:
                    voice_name, filename_base = key.split("/", 1)
                    voice_dir = self._voice_dirs.get(voice_name)
                    if voice_dir:
                        # Try primary extension first, then fallback to ogg
                        filepath = voice_dir / f"{filename_base}.{self._file_extension}"
                        if filepath.exists():
                            found = True
                        elif self._file_extension != "ogg":
                            # Fallback to .ogg (many autogen files are ogg)
                            filepath = voice_dir / f"{filename_base}.ogg"
                            if filepath.exists():
                                found = True
                        if not found:
                            logger.warning(f"Speech file not found: {filepath}")
                            continue
                    else:
                        logger.warning(f"Unknown voice: {voice_name}")
                        continue
                else:
                    # Try common voice directories: pilot, cockpit
                    # Prefer cockpit for instrument readouts
                    for voice_name in ["cockpit", "pilot"]:
                        voice_dir = self._voice_dirs.get(voice_name)
                        if voice_dir:
                            # Try primary extension first
                            filepath = voice_dir / f"{key}.{self._file_extension}"
                            if filepath.exists():
                                found = True
                                break
                            # Fallback to .ogg
                            if self._file_extension != "ogg":
                                filepath = voice_dir / f"{key}.ogg"
                                if filepath.exists():
                                    found = True
                                    break

                    if not found:
                        logger.warning(f"Message key not found: {key}")
                        continue
            else:
                # Get voice type and resolve directory from config
                voice = message_config.get("voice", "cockpit")
                voice_dir = self._voice_dirs.get(voice, self._speech_dir)

                # Build filename (use filename field from config, fallback to key name)
                filename_base = message_config.get("filename", key)
                filepath = voice_dir / f"{filename_base}.{self._file_extension}"

                # Fallback to .ogg if primary extension not found
                if not filepath.exists() and self._file_extension != "ogg":
                    filepath = voice_dir / f"{filename_base}.ogg"

                if not filepath.exists():
                    logger.warning(f"Speech file not found: {filepath}")
                    continue

            # Preload sound to avoid delays during playback
            if self._audio_engine:
                try:
                    sound = self._audio_engine.load_sound(str(filepath))
                    sound_objects.append(sound)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.error(f"Error preloading sound {filepath}: {e}")
                    continue

        if not sound_objects:
            logger.error(f"No valid speech files found for keys: {message_keys}")
            return

        # Add preloaded sounds to playback queue
        # If interrupt, clear existing queue
        if interrupt or priority == TTSPriority.CRITICAL:
            self._playback_queue.clear()
            self._playing = False
            if self._current_source_id is not None and self._audio_engine:
                with contextlib.suppress(Exception):
                    self._audio_engine.stop_source(self._current_source_id)
            self._current_source_id = None

        # Add new sounds to queue
        self._playback_queue.extend(sound_objects)

        self._state = TTSState.SPEAKING
        logger.info(f"Queued speech sequence: {message_keys} ({len(sound_objects)} files)")

        # Start playback if not already playing
        if not self._playing:
            self._play_next_in_sequence()

    def _speak_system(
        self,
        message_keys: list[str],
        priority: TTSPriority,
        interrupt: bool,
        callback: Callable[[], None] | None = None,
    ) -> None:
        """Speak using system TTS via TTS Cache Service.

        Converts message keys to text and generates speech via the TTS Cache Service
        subprocess, which handles pyttsx3 in its main thread to avoid macOS threading issues.

        Args:
            message_keys: List of message keys to speak.
            priority: Priority level.
            interrupt: If True, stop current speech.
            callback: Optional callback when done.
        """
        # Build text from message keys
        texts: list[str] = []
        voice_name = "cockpit"  # Default voice

        for key in message_keys:
            message_config = self._message_map.get(key)
            if message_config:
                # Use text from config
                text = message_config.get("text", key)
                voice_name = message_config.get("voice", "cockpit")
                texts.append(text)
            else:
                # Try to extract meaning from key
                # Handle patterns like "cockpit/number_42_autogen" or "MSG_WORD_KNOTS"
                if "/" in key:
                    voice_name, filename = key.split("/", 1)
                    # Parse autogen number keys like "number_42_autogen"
                    if filename.startswith("number_") and "_autogen" in filename:
                        num_str = filename.replace("number_", "").replace("_autogen", "")
                        texts.append(num_str)
                    else:
                        texts.append(filename.replace("_", " "))
                elif key.startswith("MSG_WORD_"):
                    # Extract word from MSG_WORD_X pattern
                    word = key.replace("MSG_WORD_", "").replace("_", " ").lower()
                    texts.append(word)
                elif key.startswith("MSG_DIGIT_"):
                    # Extract digit
                    digit = key.replace("MSG_DIGIT_", "")
                    texts.append(digit)
                elif key.startswith("MSG_"):
                    # Generic MSG_ pattern - convert underscores to spaces
                    text = key.replace("MSG_", "").replace("_", " ").lower()
                    texts.append(text)
                else:
                    texts.append(key.replace("_", " "))

        if not texts:
            logger.warning(f"No text found for keys: {message_keys}")
            return

        # Join texts into single phrase
        full_text = " ".join(texts)
        logger.info(f"System TTS speaking: '{full_text}' (voice={voice_name})")

        # Get voice settings from config
        voice_config = self._voice_configs.get(voice_name, {})
        pyttsx3_config = voice_config.get("pyttsx3", {})
        rate = pyttsx3_config.get("rate", 180)
        pyttsx3_voice = pyttsx3_config.get("voice_name")

        # Queue async generation (non-blocking)
        def on_audio_ready(audio_bytes: bytes | None) -> None:
            if not audio_bytes:
                logger.error(f"System TTS failed for: {full_text[:30]}")
                return
            # Store result for processing in update()
            self._tts_result_queue.append((audio_bytes, voice_name))

        self._request_tts_generation(full_text, voice_name, rate, pyttsx3_voice, on_audio_ready)

    def _get_realtime_tts(self, voice_name: str) -> RealtimeTTS | None:
        """Get or create RealtimeTTS instance for a voice.

        Args:
            voice_name: Voice name (pilot, cockpit, tower, etc.)

        Returns:
            RealtimeTTS instance or None if creation fails.
        """
        if voice_name not in self._realtime_tts:
            # Get voice config
            voice_config = self._voice_configs.get(voice_name, {})
            pyttsx3_config = voice_config.get("pyttsx3", {})

            # Create RealtimeTTS with voice-specific settings
            try:
                self._realtime_tts[voice_name] = RealtimeTTS(
                    rate=pyttsx3_config.get("rate", 180),
                    voice_name=pyttsx3_config.get("voice_name"),
                    cache_enabled=True,
                )
                logger.info(f"Created RealtimeTTS for voice '{voice_name}': {pyttsx3_config}")
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(f"Failed to create RealtimeTTS for voice {voice_name}: {e}")
                return None

        return self._realtime_tts[voice_name]

    def _start_tts_service(self) -> None:
        """Start the TTS Cache Service client in a background thread.

        Creates a dedicated thread with its own event loop for async operations.
        This prevents blocking the main game loop.
        """
        try:
            from airborne.tts_cache_service import TTSServiceClient

            self._tts_service_client = TTSServiceClient(auto_start=True)
            self._shutdown_requested = False

            def run_service_thread():
                """Background thread running the async event loop."""
                self._tts_service_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._tts_service_loop)

                async def main():
                    # Start the service
                    success = await self._tts_service_client.start()  # type: ignore[union-attr]
                    if not success:
                        logger.error("Failed to start TTS Cache Service")
                        return

                    logger.info("TTS Cache Service client started in background thread")

                    # Set initial context to "menu" to start pre-generation
                    # Build voice configs from parent's voice_configs
                    voices: dict[str, dict[str, Any]] = {}
                    for vname, vconfig in self._voice_configs.items():
                        pyttsx3_cfg = vconfig.get("pyttsx3", {})
                        voices[vname] = {
                            "rate": pyttsx3_cfg.get("rate", 180),
                            "voice_name": pyttsx3_cfg.get("voice_name"),
                        }
                    if voices:
                        resp = await self._tts_service_client.set_context("menu", voices)  # type: ignore
                        if resp:
                            logger.info(
                                f"Initial context set to 'menu', queued {resp.queued} items"
                            )

                    # Process requests until shutdown
                    while not self._shutdown_requested:
                        # Process pending TTS requests
                        while self._tts_request_queue:
                            try:
                                text, voice, rate, voice_name, callback = (
                                    self._tts_request_queue.popleft()
                                )
                                audio = await self._tts_service_client.generate(  # type: ignore
                                    text=text,
                                    voice=voice,
                                    rate=rate,
                                    voice_name=voice_name,
                                )
                                # Put result in result queue for main thread
                                self._tts_result_queue.append((audio, callback))
                            except Exception as e:  # pylint: disable=broad-exception-caught
                                logger.error(f"TTS generation error: {e}")
                                self._tts_result_queue.append((None, callback))

                        await asyncio.sleep(0.01)  # Small yield

                    # Shutdown
                    await self._tts_service_client.stop()  # type: ignore[union-attr]
                    logger.info("TTS Cache Service client stopped")

                self._tts_service_loop.run_until_complete(main())
                self._tts_service_loop.close()

            self._tts_service_thread = threading.Thread(
                target=run_service_thread, daemon=True, name="TTSServiceThread"
            )
            self._tts_service_thread.start()

            # Wait briefly for service to start
            import time

            time.sleep(2.0)
            logger.info("TTS Cache Service background thread started")

        except ImportError as e:
            logger.error(f"Failed to import TTSServiceClient: {e}")
            self._tts_service_client = None
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Error starting TTS Cache Service: {e}")
            self._tts_service_client = None

    def _stop_tts_service(self) -> None:
        """Stop the TTS Cache Service client."""
        if self._tts_service_client is None:
            return

        self._shutdown_requested = True

        if self._tts_service_thread and self._tts_service_thread.is_alive():
            self._tts_service_thread.join(timeout=5.0)

        self._tts_service_client = None
        self._tts_service_loop = None
        self._tts_service_thread = None
        logger.info("TTS Cache Service client stopped")

    def set_context(self, context: str) -> None:
        """Set the flight context for TTS pre-generation prioritization.

        Tells the TTS Cache Service what context the sim is in so it can
        prioritize pre-generating the most likely needed TTS items.

        Args:
            context: Flight context ("menu", "ground", "airborne").
        """
        if self._tts_mode != "system":
            return

        if self._tts_service_client is None:
            logger.warning("TTS Cache Service client not initialized")
            return

        # Build voice configs dict from our voice_configs
        voices: dict[str, dict[str, Any]] = {}
        for voice_name, voice_config in self._voice_configs.items():
            pyttsx3_config = voice_config.get("pyttsx3", {})
            voices[voice_name] = {
                "rate": pyttsx3_config.get("rate", 180),
                "voice_name": pyttsx3_config.get("voice_name"),
            }

        # Queue context change request
        def do_context_change():
            if self._tts_service_loop and self._tts_service_client:
                asyncio.run_coroutine_threadsafe(
                    self._tts_service_client.set_context(context, voices),
                    self._tts_service_loop,
                )

        # Run in background thread
        if self._tts_service_thread and self._tts_service_thread.is_alive():
            # Schedule on the service's event loop
            if self._tts_service_loop:
                self._tts_service_loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(
                        self._tts_service_client.set_context(context, voices)  # type: ignore
                    )
                )
                logger.info(f"Sent context change to TTS service: {context}")
            else:
                logger.warning("TTS service loop not available")
        else:
            logger.warning("TTS service thread not running")

    def _request_tts_generation(
        self,
        text: str,
        voice: str,
        rate: int,
        voice_name: str | None,
        callback: Callable[[bytes | None], None] | None = None,
    ) -> None:
        """Queue a TTS generation request (non-blocking).

        Args:
            text: Text to synthesize.
            voice: Logical voice name.
            rate: Speech rate.
            voice_name: Platform-specific voice name.
            callback: Called with audio bytes when ready.
        """
        if self._tts_service_client is None:
            logger.error("TTS Cache Service client not initialized")
            if callback:
                callback(None)
            return

        self._tts_request_queue.append((text, voice, rate, voice_name, callback))

    def _process_tts_results(self) -> None:
        """Process completed TTS results from background thread.

        Call this from update() to handle completed generations.
        """
        while self._tts_result_queue:
            audio_bytes, callback = self._tts_result_queue.popleft()
            if callback and callable(callback):
                callback(audio_bytes)

    def _process_tts_audio_results(self) -> None:
        """Process completed TTS audio and queue for playback.

        Called from update() to handle audio results from background thread.
        """
        # The result queue now contains (audio_bytes, voice_name) tuples
        # from the callbacks in _speak_system and speak_text
        while self._tts_result_queue:
            try:
                item = self._tts_result_queue.popleft()
                # Handle both formats: (audio, callback) and (audio, voice_name)
                audio_bytes, second = item
                if audio_bytes is None:
                    continue

                # If second is a string, it's a voice name (from our callbacks)
                if isinstance(second, str):
                    voice_name = second
                    # Load and queue for playback
                    try:
                        sound = self._audio_engine.load_sound_from_bytes(
                            audio_bytes, f"tts_{voice_name}"
                        )
                        if sound:
                            self._playback_queue.append(sound)
                            self._state = TTSState.SPEAKING
                            if not self._playing:
                                self._play_next_in_sequence()
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        logger.error(f"Error loading TTS audio: {e}")
                elif callable(second):
                    # It's a callback - call it
                    second(audio_bytes)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(f"Error processing TTS result: {e}")

    def speak_text(
        self,
        text: str,
        voice: str = "tower",
        priority: TTSPriority = TTSPriority.NORMAL,
        interrupt: bool = False,
        callback: Callable[[], None] | None = None,
    ) -> None:
        """Speak raw text directly using system TTS.

        This method is for speaking arbitrary text (like ATIS broadcasts) that
        isn't pre-recorded. Only works in system TTS mode.

        Args:
            text: Raw text to speak.
            voice: Voice name (tower, cockpit, pilot, etc.).
            priority: Priority level.
            interrupt: If True, stop current speech.
            callback: Optional callback when done.
        """
        if not self._initialized:
            return

        if not text or not text.strip():
            return

        # In self-voiced mode, we can't speak arbitrary text
        if self._tts_mode != "system":
            logger.warning("speak_text() only works in system TTS mode")
            return

        # Stop current speech if interrupt
        if interrupt or priority == TTSPriority.CRITICAL:
            self.stop()

        logger.info(f"System TTS speaking text: '{text[:50]}...' (voice={voice})")

        # Get voice settings from config
        voice_config = self._voice_configs.get(voice, {})
        pyttsx3_config = voice_config.get("pyttsx3", {})
        rate = pyttsx3_config.get("rate", 180)
        pyttsx3_voice = pyttsx3_config.get("voice_name")

        # Queue async generation (non-blocking)
        def on_audio_ready(audio_bytes: bytes | None) -> None:
            if not audio_bytes:
                logger.error(f"System TTS failed for text: {text[:30]}")
                return
            # Store result for processing in update()
            self._tts_result_queue.append((audio_bytes, voice))

        self._request_tts_generation(text, voice, rate, pyttsx3_voice, on_audio_ready)

    def _unused_speak_text_blocking(
        self,
        text: str,
        voice: str = "tower",
    ) -> None:
        """UNUSED - Old blocking implementation kept for reference.

        Load and play through FMOD - this was the blocking code.
        """
        audio_bytes: bytes | None = None  # Would be from blocking call
        try:
            sound = self._audio_engine.load_sound_from_bytes(audio_bytes, f"tts_{voice}")  # type: ignore
            if sound:
                self._playback_queue.append(sound)
                self._state = TTSState.SPEAKING
                if not self._playing:
                    self._play_next_in_sequence()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Error playing system TTS audio: {e}")

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
        Also processes completed TTS generation results from background thread.
        """
        if not self._initialized or not self._audio_engine:
            return

        # Process completed TTS results from background thread
        if self._tts_mode == "system":
            self._process_tts_audio_results()

        # Fallback polling - check if sound finished
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

"""Menu runner for main menu before game startup.

This module provides a standalone menu runner that handles the main menu
before the full game is initialized. It uses minimal resources:
- Pygame for keyboard input
- TTS cache service for speech (threaded, non-blocking)
- FMOD for click sounds

The TTS system runs in a background thread with:
- Queue for pending speech requests
- Interrupt support (new speech cancels previous)
- Non-blocking generation (UI stays responsive)

Typical usage:
    runner = MenuRunner()
    result = runner.run()
    if result == "fly":
        config = runner.get_flight_config()
        # Start the game with config
    elif result == "exit":
        sys.exit(0)
"""

import asyncio
import contextlib
import logging
import queue
import random
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

from airborne.audio.audio_facade import AudioFacade
from airborne.core.resource_path import get_resource_path
from airborne.settings import get_tts_settings
from airborne.ui.menus.main_menu import MainMenu

logger = logging.getLogger(__name__)

# Try to import FMOD for click sounds
try:
    import pyfmodex  # type: ignore[import-untyped]
    from pyfmodex.flags import MODE  # type: ignore[import-untyped]

    FMOD_AVAILABLE = True
except ImportError:
    pyfmodex = None
    MODE = None
    FMOD_AVAILABLE = False
    logger.info("pyfmodex not available, menu sounds disabled")


@dataclass
class TTSRequest:
    """Request for TTS generation."""

    text: str
    voice: str
    rate: int
    voice_name: str
    language: str
    interrupt: bool = True  # Whether to interrupt current speech


# Global voice cache shared with voice settings menu
# Key: language code, Value: list of (voice_name, display_name) tuples
_voice_cache: dict[str, list[tuple[str, str]]] = {}
_voice_cache_lock = threading.Lock()


def get_cached_voices(language: str) -> list[tuple[str, str]]:
    """Get cached voices for a language.

    Args:
        language: Language code (e.g., "en", "fr").

    Returns:
        List of (voice_name, display_name) tuples, or empty list if not cached.
    """
    with _voice_cache_lock:
        return _voice_cache.get(language, [])


def set_cached_voices(language: str, voices: list[tuple[str, str]]) -> None:
    """Set cached voices for a language.

    Args:
        language: Language code (e.g., "en", "fr").
        voices: List of (voice_name, display_name) tuples.
    """
    with _voice_cache_lock:
        _voice_cache[language] = voices
    logger.info("Cached %d voices for language %s", len(voices), language)


class MenuRunner:
    """Runs the main menu before game startup.

    This class provides a lightweight menu system that runs before the full
    game is initialized. It handles:
    - Pygame display and event loop
    - TTS via cache service (threaded, non-blocking)
    - Click sounds via FMOD
    - Menu navigation and result collection

    The TTS system uses a background thread with its own event loop to:
    - Generate speech without blocking the UI
    - Support interrupt (new speech cancels previous)
    - Queue multiple requests efficiently

    Attributes:
        result: Menu result ("fly", "exit", or None).
        flight_config: Flight configuration from menu selections.
    """

    def __init__(self) -> None:
        """Initialize the menu runner."""
        self._main_menu: MainMenu | None = None
        self._running = False
        self._result: str | None = None
        self._flight_config: dict[str, Any] = {}

        # Audio
        self._audio: AudioFacade | None = None
        self._fmod_engine: Any = None  # Will be imported and initialized
        self._tts_client: Any = None
        self._current_channel: Any = None
        self._menu_music_source_id: int | None = None  # Track music source ID

        # Current UI voice settings (for real-time preview)
        self._ui_voice_name: str = "Samantha"
        self._ui_rate: int = 180
        self._ui_language: str = "en"

        # TTS threading - async generation with queue support
        self._tts_thread: threading.Thread | None = None
        self._tts_loop: asyncio.AbstractEventLoop | None = None
        self._tts_request_queue: queue.Queue[TTSRequest | None] = queue.Queue()
        self._tts_audio_queue: deque[bytes] = deque()  # Completed audio ready to play
        self._tts_shutdown = threading.Event()
        self._tts_interrupt = threading.Event()  # Signal to interrupt current generation

        # Pygame
        self._screen: Any = None
        self._clock: Any = None
        self._font: Any = None

    @property
    def result(self) -> str | None:
        """Get menu result."""
        return self._result

    @property
    def flight_config(self) -> dict[str, Any]:
        """Get flight configuration from menu selections."""
        return self._flight_config

    def run(self) -> str | None:
        """Run the main menu loop.

        Returns:
            "fly" to start flight, "exit" to quit, or None if cancelled.
        """
        try:
            self._initialize()
            self._run_loop()
        except Exception as e:
            logger.exception("Menu runner error: %s", e)
            self._result = None
        finally:
            self._shutdown()

        return self._result

    def _initialize(self) -> None:
        """Initialize all systems for menu."""
        logger.info("Initializing menu runner...")

        # Initialize Pygame
        if pygame is None:
            raise RuntimeError("pygame not available")

        pygame.init()
        pygame.display.set_caption("AirBorne - Main Menu")
        self._screen = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
        self._clock = pygame.time.Clock()
        self._font = pygame.font.SysFont("monospace", 24)

        # Initialize FMOD for click sounds
        self._initialize_audio()

        # Initialize TTS client
        self._initialize_tts()

        # Create main menu
        self._main_menu = MainMenu()
        self._main_menu.set_callbacks(
            on_fly=self._on_fly,
            on_exit=self._on_exit,
        )
        self._main_menu.set_on_ui_voice_change(self._on_ui_voice_change)
        self._main_menu.set_on_language_change(self._on_language_change)
        self._main_menu.set_audio_callbacks(
            speak=self._speak,
            play_sound=self._play_sound,
            tts_client=self._tts_client,
            play_audio=self._play_audio,
        )
        self._main_menu.open(is_startup=True)

        # Start menu music
        self._start_menu_music()

        self._running = True
        logger.info("Menu runner initialized")

    def _initialize_audio(self) -> None:
        """Initialize FMOD audio engine and AudioFacade."""
        if not FMOD_AVAILABLE:
            logger.warning("FMOD not available, running without audio")
            return

        try:
            from airborne.audio.engine.fmod_engine import FMODEngine

            # Initialize FMOD engine
            self._fmod_engine = FMODEngine()
            self._fmod_engine.initialize({"max_channels": 32})
            logger.info("FMOD engine initialized for menu")

            # Initialize AudioFacade
            self._audio = AudioFacade(self._fmod_engine)
            logger.info("AudioFacade initialized")

        except Exception as e:
            logger.error("Failed to initialize audio: %s", e)
            self._fmod_engine = None
            self._audio = None

    def _start_menu_music(self) -> None:
        """Start playing random menu music at 0.7 volume with fade-in."""
        if not self._audio:
            logger.debug("Audio not available, skipping menu music")
            return

        try:
            # Find available menu music files
            music_dir = get_resource_path("data/musics")
            music_files = list(music_dir.glob("menu*.ogg"))

            if not music_files:
                logger.warning("No menu music files found in %s", music_dir)
                return

            # Pick a random one
            music_path = random.choice(music_files)
            logger.info("Starting menu music: %s", music_path.name)

            # Play with loop and fade-in using AudioFacade
            self._audio.music.play(
                str(music_path),
                loop=True,
                fade_in=0.0,  # No fade-in for now
                volume=0.7,  # 0.7 volume for menu music
            )

        except Exception as e:
            logger.error("Failed to start menu music: %s", e)

    def _start_menu_music_fadeout(self) -> None:
        """Start fading out the menu music over 1 second."""
        if not self._audio:
            logger.debug("Fadeout called but no audio available")
            return

        logger.info("FADEOUT: Starting menu music fadeout")
        self._audio.music.fade_out(1.0)  # 1 second fadeout
        logger.info("FADEOUT: fade_out() called")

    def _is_music_fading(self) -> bool:
        """Check if music is currently fading.

        Returns:
            True if music is fading.
        """
        if not self._audio:
            return False

        # Check if music is still playing (it will stop after fade completes)
        return self._audio.music.is_playing()

    def _stop_menu_music(self) -> None:
        """Stop menu music immediately."""
        if self._audio:
            self._audio.music.stop()
            logger.debug("Menu music stopped")

    def _initialize_tts(self) -> None:
        """Initialize TTS client and background thread."""
        from airborne.core.i18n import set_language

        # Load current UI voice settings
        try:
            settings = get_tts_settings()
            voice_settings = settings.get_voice("ui")
            self._ui_voice_name = voice_settings.voice_name
            self._ui_rate = voice_settings.rate
            self._ui_language = settings.language

            # Set i18n language from saved settings
            set_language(self._ui_language)

            logger.info(
                "UI voice: %s at %d WPM (lang=%s)",
                self._ui_voice_name,
                self._ui_rate,
                self._ui_language,
            )
        except Exception as e:
            logger.warning("Failed to load TTS settings, using defaults: %s", e)

        # Start TTS background thread with its own event loop
        self._tts_shutdown.clear()
        self._tts_interrupt.clear()
        self._tts_thread = threading.Thread(
            target=self._tts_worker_thread,
            daemon=True,
            name="MenuTTSWorker",
        )
        self._tts_thread.start()
        logger.info("TTS background thread started")

    def _tts_worker_thread(self) -> None:
        """Background thread for TTS generation.

        Runs its own asyncio event loop to handle async TTS client operations.
        Processes requests from _tts_request_queue and puts results in _tts_audio_queue.
        """
        from airborne.tts_cache_service import TTSServiceClient

        # Create event loop for this thread
        self._tts_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._tts_loop)

        async def worker_main() -> None:
            """Main async worker function."""
            # Initialize TTS client
            try:
                self._tts_client = TTSServiceClient()
                await self._tts_client.start()
                logger.info("TTS client started in background thread")
            except Exception as e:
                logger.error("Failed to start TTS client: %s", e)
                self._tts_client = None
                return

            # Pre-fetch voices for current language (before menu phrases)
            await self._prefetch_voices(self._ui_language)

            # Pre-generate menu phrases (high priority)
            await self._pregenerate_menu_phrases()

            # Process requests until shutdown
            while not self._tts_shutdown.is_set():
                try:
                    # Get request with timeout (allows checking shutdown flag)
                    try:
                        request = self._tts_request_queue.get(timeout=0.1)
                    except Exception:
                        continue

                    # None signals shutdown
                    if request is None:
                        break

                    # Check for interrupt before generating
                    if self._tts_interrupt.is_set():
                        self._tts_interrupt.clear()
                        # Clear any pending audio
                        self._tts_audio_queue.clear()

                    # Generate TTS
                    try:
                        audio_data = await self._tts_client.generate(
                            text=request.text,
                            voice=request.voice,
                            rate=request.rate,
                            voice_name=request.voice_name,
                            language=request.language,
                        )
                        if audio_data:
                            # Check if interrupted during generation
                            if self._tts_interrupt.is_set():
                                self._tts_interrupt.clear()
                                self._tts_audio_queue.clear()
                            else:
                                self._tts_audio_queue.append(audio_data)
                                logger.debug("TTS generated: %s", request.text[:30])
                    except Exception as e:
                        logger.error("TTS generation error: %s", e)

                except Exception as e:
                    logger.error("TTS worker error: %s", e)

            # Cleanup
            if self._tts_client:
                try:
                    await self._tts_client.stop()
                except Exception as e:
                    logger.error("TTS client stop error: %s", e)
            logger.info("TTS worker thread ended")

        # Run the worker
        try:
            self._tts_loop.run_until_complete(worker_main())
        except Exception as e:
            logger.error("TTS worker loop error: %s", e)
        finally:
            self._tts_loop.close()
            self._tts_loop = None

    def _run_loop(self) -> None:
        """Run the main menu event loop."""
        last_frame_time = time.time()

        while self._running:
            # Calculate delta time
            current_time = time.time()
            delta_time = current_time - last_frame_time
            last_frame_time = current_time

            # Process events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._result = "exit"
                    self._running = False
                elif event.type == pygame.KEYDOWN:
                    # Process keyboard input (don't block during fadeout)
                    self._handle_keydown(event)
                elif event.type == pygame.VIDEORESIZE:
                    self._screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)

            # Check if music fadeout completed - exit when fade completes
            if self._result == "fly" and not self._is_music_fading():
                # Fadeout complete, now we can exit
                self._running = False
                break

            # Process completed TTS audio from background thread
            self._process_tts_audio()

            # Update audio (handles fading, etc.)
            if self._audio:
                self._audio.update(delta_time)

            # Update FMOD engine
            if self._fmod_engine:
                self._fmod_engine.update()

            # Render
            self._render()
            pygame.display.flip()

            # Limit frame rate
            self._clock.tick(60)

    def _process_tts_audio(self) -> None:
        """Process completed TTS audio from background thread.

        Called from the main loop to play audio that was generated
        in the background thread.
        """
        if not self._audio:
            return

        # Play any pending audio (just the most recent one - interrupt semantics)
        while self._tts_audio_queue:
            audio_data = self._tts_audio_queue.popleft()
            # If there are more items, skip to the latest (interrupt)
            if self._tts_audio_queue:
                continue
            # Play the audio
            self._play_tts_audio_sync(audio_data)

    def _handle_keydown(self, event: Any) -> None:
        """Handle keyboard input.

        Args:
            event: Pygame keyboard event.
        """
        if self._main_menu is None:
            return

        # Get unicode character for text input
        unicode = event.unicode if hasattr(event, "unicode") else ""

        # Ignore input during fadeout (waiting for fade to complete)
        if self._result == "fly":
            return

        # Pass to menu
        self._main_menu.handle_key(event.key, unicode)

        # Check if menu closed (but not for "fly" - handled by fadeout logic)
        if not self._main_menu.is_open and self._result != "fly":
            self._running = False

    def _render(self) -> None:
        """Render the menu screen."""
        # Clear with dark background
        self._screen.fill((20, 20, 40))

        # Draw title
        title = self._font.render("AirBorne", True, (255, 255, 255))
        title_rect = title.get_rect(center=(self._screen.get_width() // 2, 50))
        self._screen.blit(title, title_rect)

        # Draw subtitle
        subtitle_font = pygame.font.SysFont("monospace", 16)
        subtitle = subtitle_font.render("Blind-Accessible Flight Simulator", True, (180, 180, 180))
        subtitle_rect = subtitle.get_rect(center=(self._screen.get_width() // 2, 80))
        self._screen.blit(subtitle, subtitle_rect)

        # Draw current menu info
        if self._main_menu:
            menu_title = self._font.render(self._main_menu.title, True, (100, 200, 255))
            menu_rect = menu_title.get_rect(center=(self._screen.get_width() // 2, 150))
            self._screen.blit(menu_title, menu_rect)

            # Draw menu items
            y_offset = 200
            for i, item in enumerate(self._main_menu.items):
                # Highlight current item
                is_current = i == self._main_menu.selected_index
                color = (255, 255, 0) if is_current else (200, 200, 200)
                prefix = "> " if is_current else "  "

                item_text = subtitle_font.render(f"{prefix}{item.label}", True, color)
                item_rect = item_text.get_rect(center=(self._screen.get_width() // 2, y_offset))
                self._screen.blit(item_text, item_rect)
                y_offset += 30

        # Draw instructions at bottom
        instructions = [
            "Up/Down: Navigate | Enter: Select | Escape: Back",
        ]
        y = self._screen.get_height() - 40
        for line in instructions:
            text = subtitle_font.render(line, True, (120, 120, 120))
            rect = text.get_rect(center=(self._screen.get_width() // 2, y))
            self._screen.blit(text, rect)
            y += 20

    def _speak(self, text: str, interrupt: bool = True) -> None:
        """Speak text using TTS (non-blocking).

        Queues the text for generation in the background thread.
        The audio will be played when ready.

        Args:
            text: Text to speak.
            interrupt: If True, stop current speech and clear pending audio.
        """
        if not text:
            return

        # Create request with current voice settings
        request = TTSRequest(
            text=text,
            voice="ui",
            rate=self._ui_rate,
            voice_name=self._ui_voice_name,
            language=self._ui_language,
            interrupt=interrupt,
        )

        # Signal interrupt if requested
        if interrupt:
            self._tts_interrupt.set()
            self._stop_current_tts()

        # Queue the request (non-blocking)
        try:
            self._tts_request_queue.put_nowait(request)
            logger.debug("TTS queued: %s", text[:30])
        except Exception as e:
            logger.error("Failed to queue TTS: %s", e)

    def _play_tts_audio_sync(self, audio_data: bytes) -> None:
        """Play TTS audio data synchronously.

        Args:
            audio_data: WAV audio bytes.
        """
        if not self._fmod_engine:
            return

        try:
            # Stop any currently playing TTS (interrupt previous message)
            self._stop_current_tts()

            # Write to temp file and play via FMODEngine
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_data)
                temp_path = f.name

            # Load sound and play (TTS is 2D, UI category)
            sound = self._fmod_engine.load_sound(temp_path, preload=True, loop_mode=False)
            source_id = self._fmod_engine.play_2d(sound, loop=False, volume=1.0)

            # Store channel reference for interrupt support
            if source_id is not None:
                self._current_channel = self._fmod_engine.get_channel(source_id)

            # Clean up temp file (FMOD has loaded it by now)
            Path(temp_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error("TTS playback error: %s", e)

    def _stop_current_tts(self) -> None:
        """Stop any currently playing TTS audio."""
        if self._current_channel is not None:
            with contextlib.suppress(Exception):
                self._current_channel.stop()
            self._current_channel = None

    def _play_sound(self, path: str, volume: float = 1.0) -> None:
        """Play a sound file.

        Args:
            path: Path to sound file (or sound name like "knob").
            volume: Volume level (0.0 to 1.0).
        """
        if not self._audio:
            return

        try:
            # Map named sounds to actual file paths
            sounds_dir = get_resource_path("assets/sounds/aircraft")
            sound_map = {
                "knob": str(sounds_dir / "click_knob.mp3"),
                "switch": str(sounds_dir / "click_switch.mp3"),
                "button": str(sounds_dir / "click_button.mp3"),
            }

            # Resolve sound path
            sound_path = sound_map.get(path, path)

            # Check if file exists
            if not Path(sound_path).exists():
                logger.warning("Sound file not found: %s", sound_path)
                return

            # Play via AudioFacade (UI category for menu sounds)
            self._audio.sfx.play(sound_path, category="ui", volume=volume, loop=False)

        except Exception as e:
            logger.error("Sound playback error: %s", e)

    def _play_audio(self, audio_data: bytes) -> None:
        """Play raw WAV audio bytes.

        Args:
            audio_data: WAV audio bytes.
        """
        # Reuse the sync playback method
        self._play_tts_audio_sync(audio_data)

    async def _prefetch_voices(self, language: str) -> None:
        """Pre-fetch available voices for a language from the TTS service.

        Stores voices in the global cache for use by voice settings menu.
        Called during startup and when language changes.

        Args:
            language: Language code (e.g., "en", "fr").
        """
        if not self._tts_client:
            return

        try:
            response = await self._tts_client.list_voices(language=language)
            if response and response.voices:
                # Convert to (name, display) tuples
                voices: list[tuple[str, str]] = []
                for voice in response.voices:
                    name = voice.name
                    # Create display name with language variant
                    lang = voice.language or ""
                    if "_" in lang:
                        variant = lang.split("_")[1].upper()
                        display = f"{name} ({variant})"
                    else:
                        display = name
                    voices.append((name, display))

                # Sort by display name
                voices.sort(key=lambda x: x[1])
                set_cached_voices(language, voices)
            else:
                logger.warning("No voices returned for language %s", language)
        except Exception as e:
            logger.warning("Failed to prefetch voices for %s: %s", language, e)

    async def _pregenerate_menu_phrases(self) -> None:
        """Pre-generate common menu phrases for faster TTS response.

        Queues all translatable menu strings for background generation.
        This ensures menu navigation feels responsive even on first use.
        """
        if not self._tts_client:
            return

        from airborne.core.i18n import t

        # Priority 0: Highest priority - immediate menu items
        # These are announced immediately on menu open
        priority_phrases: list[str] = [
            # Welcome and main menu items
            t("menu.main.welcome"),
            t("menu.main.title"),
            t("menu.main.fly"),
            t("menu.main.fly_settings"),
            t("menu.main.settings"),
            t("menu.main.exit"),
            t("menu.main.starting_flight"),
            t("menu.main.goodbye"),
            # Fly settings
            t("menu.fly_settings.title"),
            t("menu.fly_settings.flight_plan"),
            t("menu.fly_settings.aircraft_selection"),
            # Settings
            t("menu.settings.title"),
            t("menu.settings.voice_settings"),
            t("menu.settings.language"),
            # Common
            t("common.back"),
            t("common.go_back"),
            t("common.save"),
            t("common.cancel"),
            t("common.disabled"),
            t("common.saved"),
            t("common.selected"),
            # Item counts for menu announcements
            "1 items.",
            "2 items.",
            "3 items.",
            "4 items.",
            "5 items.",
        ]

        # Remove duplicates while preserving order
        seen: set[str] = set()
        unique_phrases: list[str] = []
        for phrase in priority_phrases:
            if phrase and phrase not in seen:
                seen.add(phrase)
                unique_phrases.append(phrase)

        if not unique_phrases:
            return

        try:
            response = await self._tts_client.queue(
                texts=unique_phrases,
                voice="ui",
                rate=self._ui_rate,
                voice_name=self._ui_voice_name,
                priority=0,  # Highest priority
            )
            if response and response.queued > 0:
                logger.info("Queued %d menu phrases for pre-generation", response.queued)
        except Exception as e:
            logger.warning("Failed to queue menu phrases: %s", e)

    def _on_ui_voice_change(self, voice_name: str, rate: int) -> None:
        """Handle UI voice settings change.

        Args:
            voice_name: New voice name.
            rate: New speech rate in WPM.
        """
        self._ui_voice_name = voice_name
        self._ui_rate = rate
        logger.debug("UI voice changed: %s at %d WPM", voice_name, rate)

    def _on_language_change(self, language: str) -> None:
        """Handle language change - trigger voice cache refresh.

        Args:
            language: New language code.
        """
        if language == self._ui_language:
            return

        self._ui_language = language
        logger.info("Language changed to %s, requesting voice cache refresh", language)

        # Queue a voice prefetch request to the TTS thread
        # We do this by putting a special request that the worker handles
        self._request_voice_prefetch(language)

    def _request_voice_prefetch(self, language: str) -> None:
        """Request voice prefetch from TTS background thread.

        Args:
            language: Language code to prefetch voices for.
        """
        # Create a special request type for voice prefetch
        # The worker thread will check for this and call _prefetch_voices
        # For now, we use a simple approach: schedule it via the event loop
        if self._tts_loop and not self._tts_loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._prefetch_voices(language), self._tts_loop)
            logger.debug("Scheduled voice prefetch for language %s", language)

    def _on_fly(self) -> None:
        """Handle Fly! selection.

        Starts the menu music fadeout. The actual exit happens when
        the fadeout completes (handled in _run_loop).
        """
        self._result = "fly"
        if self._main_menu:
            self._flight_config = self._main_menu.get_flight_config()
        logger.info("Fly selected with config: %s", self._flight_config)

        # Start music fadeout - menu will close when fade completes
        self._start_menu_music_fadeout()

    def _on_exit(self) -> None:
        """Handle Exit selection."""
        self._result = "exit"
        logger.info("Exit selected")

    def _shutdown(self) -> None:
        """Shutdown all systems."""
        logger.info("Shutting down menu runner...")

        # Stop TTS background thread
        self._tts_shutdown.set()
        # Send None to wake up the thread
        with contextlib.suppress(Exception):
            self._tts_request_queue.put_nowait(None)

        if self._tts_thread and self._tts_thread.is_alive():
            self._tts_thread.join(timeout=5.0)
            if self._tts_thread.is_alive():
                logger.warning("TTS thread did not stop cleanly")
        self._tts_thread = None

        # Shutdown AudioFacade (stops music, clears effects)
        if self._audio:
            self._audio.shutdown()

        # Shutdown FMOD engine
        if self._fmod_engine:
            try:
                self._fmod_engine.shutdown()
            except Exception as e:
                logger.error("FMOD engine shutdown error: %s", e)

        # Shutdown Pygame
        if pygame:
            pygame.quit()

        logger.info("Menu runner shutdown complete")

    def get_flight_config(self) -> dict[str, Any]:
        """Get flight configuration from menu.

        Returns:
            Dictionary with departure, arrival, and aircraft.
        """
        return self._flight_config

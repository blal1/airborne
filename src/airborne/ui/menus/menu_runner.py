"""Menu runner for main menu before game startup.

This module provides a standalone menu runner that handles the main menu
before the full game is initialized. It uses minimal resources:
- Pygame for keyboard input
- Shared TTSService for speech (passed from main)
- FMOD for click sounds

TTS operations are non-blocking: speak() queues requests, and audio is
delivered via callbacks invoked during TTSService.update().

Typical usage:
    runner = MenuRunner(tts_service=tts_service)
    result = runner.run()
    if result == "fly":
        config = runner.get_flight_config()
        # Start the game with config
    elif result == "exit":
        sys.exit(0)
"""

import contextlib
import logging
import random
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from airborne.audio.tts_service import TTSService

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

from airborne.audio.audio_facade import AudioFacade
from airborne.audio.tts_service import TTSPriority
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
    - TTS via shared TTSService (passed from main)
    - Click sounds via FMOD
    - Menu navigation and result collection

    TTS operations use the shared TTSService facade:
    - speak() queues text for generation with priority
    - Audio is delivered via callbacks during TTSService.update()
    - The service handles all async/threading internally

    Attributes:
        result: Menu result ("fly", "exit", or None).
        flight_config: Flight configuration from menu selections.
    """

    def __init__(self, tts_service: "TTSService | None" = None) -> None:
        """Initialize the menu runner.

        Args:
            tts_service: Shared TTSService instance for TTS operations.
        """
        self._main_menu: MainMenu | None = None
        self._running = False
        self._result: str | None = None
        self._flight_config: dict[str, Any] = {}

        # Shared TTS service (from main)
        self._tts_service = tts_service
        
        # Direct TTS cache fallback (used if WebSocket service fails)
        self._direct_tts_cache: Any | None = None
        self._tts_service_failed = False

        # Audio
        self._audio: AudioFacade | None = None
        self._fmod_engine: Any = None  # Will be imported and initialized
        self._current_channel: Any = None
        self._menu_music_source_id: int | None = None  # Track music source ID

        # Current UI voice settings (for real-time preview)
        self._ui_voice_name: str = "Samantha"
        self._ui_rate: int = 180
        self._ui_language: str = "en"

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
        self._screen = pygame.display.set_mode((800, 600), pygame.RESIZABLE | pygame.SHOWN)
        self._clock = pygame.time.Clock()
        self._font = pygame.font.SysFont("monospace", 24)
        
        # Ensure window has focus and is ready for input
        pygame.event.pump()  # Process pending events
        pygame.display.flip()  # Update display

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
            tts_client=None,  # No longer used - TTSService handles TTS
            play_audio=self._play_audio,
        )
        self._main_menu.open(is_startup=True)

        # Start menu music
        self._start_menu_music()
        
        # Play startup sound to confirm menu is ready (even if TTS fails)
        self._play_startup_sound()
        
        # Test TTS immediately to detect if it's really working
        # This forces fallback activation if WebSocket failed
        self._test_tts_on_startup()

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

        self._audio.music.fade_out(2.0)  # 1 second fadeout

    def _is_music_fading(self) -> bool:
        """Check if music is currently fading.

        Returns:
            True if music is fading.
        """
        if not self._audio:
            return False

        # Check if music is still playing (it will stop after fade completes)
        return self._audio.music.is_playing()
    
    def _initialize_direct_tts_fallback(self) -> None:
        """Initialize direct TTS cache as fallback when WebSocket service fails.
        
        This loads cached TTS files directly from disk, bypassing the service.
        """
        try:
            from airborne.audio.direct_tts_cache import DirectTTSCache
            
            self._direct_tts_cache = DirectTTSCache()
            
            if self._direct_tts_cache.has_cache():
                logger.info(
                    "DirectTTSCache fallback initialized - will use cached TTS files"
                )
            else:
                logger.warning("No cached TTS files found - menu will be silent")
        except Exception as e:
            logger.error("Failed to initialize direct TTS cache: %s", e)
            self._direct_tts_cache = None
    
    def _try_direct_tts_cache(self, text: str) -> bytes | None:
        """Try to load audio from direct TTS cache.
        
        Args:
            text: Text to look up in cache.
            
        Returns:
            WAV audio bytes if found in cache, None otherwise.
        """
        if not self._direct_tts_cache:
            return None
        
        try:
            return self._direct_tts_cache.get_cached_audio(
                text=text,
                voice_name=self._ui_voice_name,
                rate=self._ui_rate,
                language=self._ui_language
            )
        except Exception as e:
            logger.error("Direct TTS cache lookup failed: %s", e)
            return None
    
    def _generate_with_kokoro(self, text: str) -> bytes | None:
        """Generate TTS audio directly using KokoroTTS (bypass WebSocket service).
        
        This is used as a fallback when the WebSocket TTS service is unavailable.
        
        Args:
            text: Text to synthesize.
            
        Returns:
            WAV audio bytes if successful, None otherwise.
        """
        try:
            from kokoro_onnx import Kokoro
            import soundfile as sf
            import tempfile
            from pathlib import Path
            from airborne.core.resource_path import get_resource_path
            
            # Initialize Kokoro once (cached)
            if not hasattr(self, '_kokoro_instance'):
                model_path = get_resource_path("assets/models/kokoro-v1.0.onnx")
                voices_path = get_resource_path("assets/models/voices-v1.0.bin")
                
                logger.info("Initializing KokoroTTS for direct generation...")
                self._kokoro_instance = Kokoro(
                    model_path=str(model_path),
                    voices_path=str(voices_path)
                )
                logger.info("KokoroTTS initialized successfully")
            
            # Map voice name to Kokoro voice
            voice_map = {
                "Samantha": "af_bella",  # Clear, professional (UI)
                "Karen": "af_sarah",     # Professional (cockpit)
                "Daniel": "am_adam",     # Professional (ATC)
                "Thomas": "am_michael",  # Warm (ground)
            }
            
            kokoro_voice = voice_map.get(self._ui_voice_name, "af_bella")
            
            # Calculate speed from WPM rate
            # Normal speaking is around 150-180 WPM
            speed = 1.0
            if self._ui_rate:
                speed = 0.5 + (self._ui_rate / 180.0) * 0.6
                speed = max(0.7, min(1.3, speed))
            
            logger.debug(
                "Generating TTS with Kokoro: voice=%s, speed=%.2f, text=%s",
                kokoro_voice,
                speed,
                text[:30]
            )
            
            # Generate speech
            samples, sample_rate = self._kokoro_instance.create(
                text=text,
                voice=kokoro_voice,
                lang='en-us',
                speed=speed
            )
            
            # Write to temporary WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = Path(f.name)
            
            sf.write(str(temp_path), samples, sample_rate)
            
            # Read WAV bytes
            audio_bytes = temp_path.read_bytes()
            
            # Clean up temp file
            temp_path.unlink(missing_ok=True)
            
            logger.debug("KokoroTTS generated %d bytes", len(audio_bytes))
            return audio_bytes
            
        except ImportError as e:
            logger.error("KokoroTTS not available: %s. Install with: pip install kokoro-onnx soundfile", e)
            return None
        except Exception as e:
            logger.error("KokoroTTS generation failed: %s", e)
            return None
    
    def _test_tts_on_startup(self) -> None:
        """Test TTS service at startup to detect failures early.
        
        Even if TTSService claims to be running, the WebSocket client
        might have failed. This test forces an actual TTS call to detect
        failures and activate fallback immediately.
        """
        if not self._tts_service or self._tts_service_failed:
            return
        
        # Try a silent test - just queue and see if it fails
        test_text = "test"
        try:
            priority = TTSPriority.LOW
            self._tts_service.speak(
                text=test_text,
                voice="ui",
                priority=priority,
                interrupt=False,
                on_audio=lambda audio: None,  # Discard result
            )
            logger.debug("TTS service test successful")
        except Exception as e:
            # Service failed - activate fallback immediately
            logger.warning("TTS service test failed (%s), activating fallback NOW", e)
            self._tts_service_failed = True
            self._initialize_direct_tts_fallback()

    def _stop_menu_music(self) -> None:
        """Stop menu music immediately."""
        if self._audio:
            self._audio.music.stop()
            logger.debug("Menu music stopped")
    
    def _play_startup_sound(self) -> None:
        """Play a startup sound to confirm menu is ready.
        
        This provides audio feedback even if TTS fails, so the user
        knows the menu is ready for interaction.
        """
        if not self._audio:
            logger.debug("No audio available for startup sound")
            return
        
        try:
            # Play button click sound to signal readiness
            sounds_dir = get_resource_path("assets/sounds/aircraft")
            click_path = sounds_dir / "click_button.mp3"
            
            if click_path.exists():
                self._audio.sfx.play(str(click_path), category="ui", volume=0.8, loop=False)
                logger.info("Menu startup sound played")
            else:
                logger.warning("Startup sound file not found: %s", click_path)
        except Exception as e:
            logger.error("Failed to play startup sound: %s", e)

    def _initialize_tts(self) -> None:
        """Initialize TTS settings from configuration.

        The actual TTS service is passed from main.py and handles all
        async/threading internally. This just loads voice settings.
        """
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

        # Log TTS service status
        if self._tts_service and self._tts_service.is_running:
            logger.info("Using shared TTSService for menu TTS")
        else:
            logger.warning("TTSService not available or failed to start")
            self._tts_service_failed = True
            self._initialize_direct_tts_fallback()

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

            # Process TTS results (invokes callbacks on main thread)
            if self._tts_service:
                self._tts_service.update()

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

        Queues the text for generation via TTSService. Audio will be
        delivered via callback and played when update() is called.
        
        If TTSService has failed, attempts to load from direct cache,
        then generates with KokoroTTS if not cached.

        Args:
            text: Text to speak.
            interrupt: If True, flush lower priority pending requests.
        """
        if not text:
            return

        # If TTS service failed, use direct generation
        if self._tts_service_failed:
            # Try cache first (fastest)
            audio = self._try_direct_tts_cache(text)
            
            # If not in cache, generate with KokoroTTS
            if not audio:
                logger.debug("Not in cache, generating with KokoroTTS: %s", text[:30])
                audio = self._generate_with_kokoro(text)
            else:
                logger.debug("Playing from cache: %s", text[:30])
            
            # Play if we got audio (from cache or generation)
            if audio:
                if interrupt:
                    self._stop_current_tts()
                self._play_tts_audio_sync(audio)
            else:
                logger.warning("No TTS audio available for: %s", text[:30])
            return

        if not self._tts_service:
            logger.debug("TTSService not available, skipping: %s", text[:30])
            # Activate fallback if not already done
            if not self._tts_service_failed and not self._direct_tts_cache:
                logger.info("TTSService unavailable, activating direct generation fallback")
                self._tts_service_failed = True
                self._initialize_direct_tts_fallback()
            return

        try:
            # Stop any currently playing TTS if interrupting
            if interrupt:
                self._stop_current_tts()

            # Queue via TTSService with callback for audio playback
            # Use NORMAL priority for UI speech (can be flushed by CRITICAL)
            priority = TTSPriority.HIGH if interrupt else TTSPriority.NORMAL
            self._tts_service.speak(
                text=text,
                voice="ui",
                priority=priority,
                interrupt=interrupt,
                on_audio=self._play_tts_audio_sync,
            )
            logger.debug("TTS queued via TTSService: %s", text[:30])
        except Exception as e:
            # TTS service failed - activate direct generation fallback
            logger.warning("TTS speak failed (%s), activating direct generation fallback", e)
            
            if not self._tts_service_failed:
                self._tts_service_failed = True
                self._initialize_direct_tts_fallback()
            
            # Try cache first, then generate
            audio = self._try_direct_tts_cache(text)
            if not audio:
                logger.debug("Generating with KokoroTTS after service failure: %s", text[:30])
                audio = self._generate_with_kokoro(text)
            
            if audio:
                logger.debug("Recovered with TTS: %s", text[:30])
                if interrupt:
                    self._stop_current_tts()
                self._play_tts_audio_sync(audio)
            else:
                logger.warning("Unable to generate TTS for: %s", text[:30])

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
        """Handle language change.

        Args:
            language: New language code.
        """
        if language == self._ui_language:
            return

        self._ui_language = language
        logger.info("Language changed to %s", language)

        # Note: Voice prefetch is not implemented yet.
        # TODO: Add list_voices to TTSService to support voice selection.

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

        # Note: TTSService lifecycle is managed by main.py, not here.
        # We don't shutdown the service since it's shared with the game.

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

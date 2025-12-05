"""Sound manager coordinating audio engine and TTS.

This module provides a high-level interface for managing all audio in the
flight simulator, coordinating the audio engine, TTS, and sound effects.

Typical usage example:
    from airborne.audio.sound_manager import SoundManager

    manager = SoundManager()
    manager.initialize(audio_engine, tts_provider)
    manager.play_sound_3d("engine.wav", position)
    manager.speak("Engine started")
"""

from typing import Any

from airborne.audio.engine.base import IAudioEngine, Sound, Vector3
from airborne.audio.spatial.cockpit_spatial import CockpitSpatialManager
from airborne.audio.tts.base import ITTSProvider, TTSPriority
from airborne.core.logging_system import get_logger
from airborne.core.resource_path import get_resource_path

logger = get_logger(__name__)


class SoundManager:
    """High-level sound manager.

    Coordinates audio engine and TTS provider, manages sound caching,
    and provides convenient methods for common audio operations.

    Examples:
        >>> from airborne.audio.engine.pybass_engine import PyBASSEngine
        >>> from airborne.audio.tts.pyttsx_provider import PyTTSXProvider
        >>>
        >>> manager = SoundManager()
        >>> manager.initialize(PyBASSEngine(), PyTTSXProvider())
        >>> manager.play_sound_2d("beep.wav")
        >>> manager.speak("Welcome to AirBorne")
    """

    def __init__(self) -> None:
        """Initialize the sound manager (not started yet)."""
        self._audio_engine: IAudioEngine | None = None
        self._tts_provider: ITTSProvider | None = None
        self._sound_cache: dict[str, Sound] = {}
        self._master_volume = 1.0
        self._tts_enabled = True

        # Active sound sources (for continuous sounds like engine)
        self._engine_source_id: int | None = None
        self._engine_start_source_id: int | None = None  # For engine start sound
        self._wind_source_id: int | None = None
        self._battery_loop_source_id: int | None = None
        self._battery_on_source_id: int | None = None  # For battery on one-shot

        # Engine sound paths (start/idle/shutdown)
        self._engine_start_path: str | None = None
        self._engine_idle_path: str | None = None
        self._engine_shutdown_path: str | None = None

        # Battery sound paths (on/off/loop)
        self._battery_on_path: str | None = None
        self._battery_off_path: str | None = None
        self._battery_loop_path: str | None = None

        # Engine sound pitch configuration (can be overridden per aircraft)
        self._engine_pitch_idle = 0.7  # Pitch at 0% throttle
        self._engine_pitch_full = 1.3  # Pitch at 100% throttle

        # Engine sound sequence state
        self._engine_sequence_active = False
        self._engine_sequence_callback: Any = None  # Callback when idle sound starts

        # Battery sound sequence state
        self._battery_sequence_active = False
        self._battery_sequence_callback: Any = None  # Callback when battery is truly ON

        # Cockpit spatial audio manager
        self._spatial_manager: CockpitSpatialManager | None = None

    def initialize(
        self,
        audio_engine: IAudioEngine,
        tts_provider: ITTSProvider,
        audio_config: dict[str, Any] | None = None,
        tts_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize audio systems.

        Args:
            audio_engine: Audio engine instance.
            tts_provider: TTS provider instance.
            audio_config: Configuration for audio engine.
            tts_config: Configuration for TTS provider.
        """
        self._audio_engine = audio_engine
        self._tts_provider = tts_provider

        # Initialize audio engine
        if audio_config is None:
            audio_config = {"sample_rate": 44100, "enable_3d": True}
        self._audio_engine.initialize(audio_config)

        # Initialize TTS only if config provided (may already be initialized)
        if tts_config is not None:
            self._tts_provider.initialize(tts_config)

        logger.info("Sound manager initialized")

    def load_cockpit_preset(self, preset_name: str, presets_dir: str) -> bool:
        """Load cockpit spatial audio preset.

        Args:
            preset_name: Name of the preset (e.g., "cessna_172", "dr400").
            presets_dir: Directory containing preset YAML files.

        Returns:
            True if loaded successfully, False otherwise.
        """
        self._spatial_manager = CockpitSpatialManager()
        if self._spatial_manager.load_preset(preset_name, presets_dir):
            logger.info(f"Loaded cockpit spatial preset: {preset_name}")
            return True
        else:
            logger.warning(f"Failed to load cockpit preset: {preset_name}")
            self._spatial_manager = None
            return False

    def shutdown(self) -> None:
        """Shutdown all audio systems."""
        if self._tts_provider:
            self._tts_provider.shutdown()

        if self._audio_engine:
            # Unload all cached sounds
            for sound in list(self._sound_cache.values()):
                try:
                    self._audio_engine.unload_sound(sound)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.error("Error unloading sound: %s", e)

            self._audio_engine.shutdown()

        self._sound_cache.clear()
        logger.info("Sound manager shutdown")

    def load_sound(self, path: str, preload: bool = True) -> Sound:
        """Load a sound file.

        Args:
            path: Path to sound file.
            preload: Whether to load into memory.

        Returns:
            Loaded sound.
        """
        if not self._audio_engine:
            raise RuntimeError("Sound manager not initialized")

        # Check cache
        if path in self._sound_cache:
            return self._sound_cache[path]

        # Load sound
        sound = self._audio_engine.load_sound(path, preload)
        self._sound_cache[path] = sound
        return sound

    def play_sound_2d(
        self,
        path: str,
        volume: float = 1.0,
        pitch: float = 1.0,
        loop: bool = False,
    ) -> int:
        """Play a sound in 2D.

        Args:
            path: Path to sound file.
            volume: Volume level.
            pitch: Pitch multiplier.
            loop: Whether to loop.

        Returns:
            Source ID.
        """
        if not self._audio_engine:
            raise RuntimeError("Sound manager not initialized")

        sound = self.load_sound(path)
        return self._audio_engine.play_2d(sound, volume, pitch, loop)

    def play_sound_3d(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        path: str,
        position: Vector3,
        velocity: Vector3 | None = None,
        volume: float = 1.0,
        pitch: float = 1.0,
        loop: bool = False,
    ) -> int:
        """Play a sound in 3D.

        Args:
            path: Path to sound file.
            position: 3D position.
            velocity: 3D velocity.
            volume: Volume level.
            pitch: Pitch multiplier.
            loop: Whether to loop.

        Returns:
            Source ID.
        """
        if not self._audio_engine:
            raise RuntimeError("Sound manager not initialized")

        sound = self.load_sound(path)
        return self._audio_engine.play_3d(sound, position, velocity, volume, pitch, loop)

    def stop_sound(self, source_id: int) -> None:
        """Stop a playing sound.

        Args:
            source_id: Source ID.
        """
        if self._audio_engine:
            self._audio_engine.stop_source(source_id)

    def update_listener(
        self,
        position: Vector3,
        forward: Vector3,
        up: Vector3,
        velocity: Vector3 | None = None,
    ) -> None:
        """Update listener position and orientation.

        Args:
            position: Listener position.
            forward: Forward direction.
            up: Up direction.
            velocity: Listener velocity.
        """
        if self._audio_engine:
            self._audio_engine.set_listener(position, forward, up, velocity)

    def speak(
        self,
        text: str,
        priority: TTSPriority = TTSPriority.NORMAL,
        interrupt: bool = False,
    ) -> None:
        """Speak text using TTS.

        Args:
            text: Text to speak.
            priority: Speech priority.
            interrupt: Whether to interrupt current speech.
        """
        if not self._tts_enabled or not self._tts_provider:
            return

        self._tts_provider.speak(text, priority, interrupt)

    def stop_speech(self) -> None:
        """Stop current speech."""
        if self._tts_provider:
            self._tts_provider.stop()

    def set_master_volume(self, volume: float) -> None:
        """Set master volume for sounds.

        Args:
            volume: Volume level (0.0 to 1.0).
        """
        self._master_volume = max(0.0, min(1.0, volume))
        if self._audio_engine:
            self._audio_engine.set_master_volume(self._master_volume)

    def set_tts_enabled(self, enabled: bool) -> None:
        """Enable or disable TTS.

        Args:
            enabled: Whether TTS is enabled.
        """
        self._tts_enabled = enabled
        logger.info("TTS %s", "enabled" if enabled else "disabled")

    def is_speaking(self) -> bool:
        """Check if TTS is currently speaking.

        Returns:
            True if speaking.
        """
        if self._tts_provider:
            return self._tts_provider.is_speaking()
        return False

    def set_engine_sound_paths(
        self,
        start_path: str | None = None,
        idle_path: str | None = None,
        shutdown_path: str | None = None,
    ) -> None:
        """Configure engine sound file paths.

        Args:
            start_path: Path to engine start sound (plays once).
            idle_path: Path to engine idle/running sound (loops).
            shutdown_path: Path to engine shutdown sound (plays once).
        """
        self._engine_start_path = start_path
        self._engine_idle_path = idle_path
        self._engine_shutdown_path = shutdown_path
        logger.debug(
            f"Engine sound paths configured: start={start_path}, idle={idle_path}, shutdown={shutdown_path}"
        )

    def set_battery_sound_paths(
        self,
        on_path: str | None = None,
        off_path: str | None = None,
        loop_path: str | None = None,
    ) -> None:
        """Configure battery sound file paths.

        Args:
            on_path: Path to battery on sound (plays once at startup).
            off_path: Path to battery off sound (plays once at shutdown).
            loop_path: Path to battery loop sound (loops while battery is on).
        """
        self._battery_on_path = on_path
        self._battery_off_path = off_path
        self._battery_loop_path = loop_path
        logger.debug(
            f"Battery sound paths configured: on={on_path}, off={off_path}, loop={loop_path}"
        )

    def start_engine_sound(self, path: str | None = None) -> None:
        """Start looping engine sound.

        Args:
            path: Path to engine sound file (default: assets/sounds/aircraft/engine.wav).
        """
        if path is None:
            path = str(get_resource_path("assets/sounds/aircraft/engine.wav"))

        if not self._audio_engine:
            return

        # Stop existing engine sound
        if self._engine_source_id is not None:
            self._audio_engine.stop_source(self._engine_source_id)

        # Start new looping engine sound at low pitch/volume (idle)
        try:
            self._engine_source_id = self.play_sound_2d(path, volume=0.3, pitch=0.5, loop=True)
            logger.debug("Engine sound started")
        except FileNotFoundError:
            logger.warning(f"Engine sound not found: {path}")

    def start_engine_sequence(self, on_idle_callback: Any = None) -> None:
        """Start engine sound sequence: start.wav -> idle.wav (looping).

        Plays the start sound once, then transitions to the idle sound (looping).
        Calls on_idle_callback when idle sound starts.

        Args:
            on_idle_callback: Callback to call when idle sound starts (engine running).
        """
        if not self._audio_engine:
            return

        # If we have configured sound paths, use the sequence
        if self._engine_start_path and self._engine_idle_path:
            # Stop any existing engine sounds
            if self._engine_source_id is not None:
                self._audio_engine.stop_source(self._engine_source_id)
                self._engine_source_id = None
            if self._engine_start_source_id is not None:
                self._audio_engine.stop_source(self._engine_start_source_id)
                self._engine_start_source_id = None

            # Start the start sound (one-shot)
            try:
                self._engine_start_source_id = self.play_sound_2d(
                    self._engine_start_path, volume=0.8, pitch=1.0, loop=False
                )
                self._engine_sequence_active = True
                self._engine_sequence_callback = on_idle_callback
                logger.info("Engine start sequence initiated (start sound playing)")
            except FileNotFoundError:
                logger.warning(f"Engine start sound not found: {self._engine_start_path}")
                # Fall back to starting idle immediately
                self._start_engine_idle()
        else:
            # Fall back to old behavior (use idle path directly)
            self.start_engine_sound(self._engine_idle_path)

    def _start_engine_idle(self) -> None:
        """Start the engine idle sound (internal helper)."""
        if not self._audio_engine or not self._engine_idle_path:
            return

        # Stop start sound if still playing
        if self._engine_start_source_id is not None:
            self._audio_engine.stop_source(self._engine_start_source_id)
            self._engine_start_source_id = None

        # Start idle sound (looping)
        try:
            # Load with loop mode enabled (like battery loop)
            idle_sound = self._audio_engine.load_sound(
                self._engine_idle_path,
                preload=True,
                loop_mode=True,
            )
            self._engine_source_id = self._audio_engine.play_2d(
                idle_sound, volume=0.3, pitch=self._engine_pitch_idle, loop=True
            )
            logger.info("Engine idle sound started (looping)")

            # Call callback if registered
            if self._engine_sequence_callback:
                callback = self._engine_sequence_callback
                self._engine_sequence_callback = None
                callback()
        except FileNotFoundError:
            logger.warning(f"Engine idle sound not found: {self._engine_idle_path}")

        self._engine_sequence_active = False

    def stop_engine_sound(self, play_shutdown: bool = True) -> None:
        """Stop engine sound and optionally play shutdown sound.

        Args:
            play_shutdown: Whether to play the shutdown sound.
        """
        if not self._audio_engine:
            return

        # Stop any active engine sounds
        if self._engine_source_id is not None:
            self._audio_engine.stop_source(self._engine_source_id)
            self._engine_source_id = None

        if self._engine_start_source_id is not None:
            self._audio_engine.stop_source(self._engine_start_source_id)
            self._engine_start_source_id = None

        # Play shutdown sound if configured and requested
        if play_shutdown and self._engine_shutdown_path:
            try:
                self.play_sound_2d(self._engine_shutdown_path, volume=0.8, pitch=1.0, loop=False)
                logger.info("Engine shutdown sound playing")
            except FileNotFoundError:
                logger.warning(f"Engine shutdown sound not found: {self._engine_shutdown_path}")

        self._engine_sequence_active = False
        self._engine_sequence_callback = None

    def update_engine_sound(self, throttle: float) -> None:
        """Update engine sound based on throttle.

        Args:
            throttle: Throttle position (0.0 to 1.0).
        """
        if not self._audio_engine or self._engine_source_id is None:
            return

        # Map throttle to pitch using configured range
        pitch = self._engine_pitch_idle + (
            throttle * (self._engine_pitch_full - self._engine_pitch_idle)
        )
        # Map throttle to volume (0.3 at idle to 1.0 at full throttle)
        volume = 0.3 + (throttle * 0.7)

        self._audio_engine.update_source_pitch(self._engine_source_id, pitch)
        self._audio_engine.update_source_volume(self._engine_source_id, volume)

    def set_engine_pitch_range(self, pitch_idle: float, pitch_full: float) -> None:
        """Configure engine sound pitch range.

        Args:
            pitch_idle: Audio pitch at 0% throttle.
            pitch_full: Audio pitch at 100% throttle.
        """
        self._engine_pitch_idle = pitch_idle
        self._engine_pitch_full = pitch_full
        logger.debug(f"Engine pitch range set: {pitch_idle} to {pitch_full}")

    def start_wind_sound(self, path: str | None = None) -> None:
        """Start looping wind sound.

        Args:
            path: Path to wind sound file (default: assets/sounds/aircraft/wind.mp3).
        """
        if path is None:
            path = str(get_resource_path("assets/sounds/aircraft/wind.mp3"))

        if not self._audio_engine:
            return

        # Stop existing wind sound
        if self._wind_source_id is not None:
            self._audio_engine.stop_source(self._wind_source_id)

        # Start new looping wind sound at low volume (stopped)
        try:
            self._wind_source_id = self.play_sound_2d(path, volume=0.0, pitch=1.0, loop=True)
            logger.debug("Wind sound started")
        except FileNotFoundError:
            logger.warning(f"Wind sound not found: {path}")

    def update_wind_sound(self, airspeed: float) -> None:
        """Update wind sound based on airspeed.

        Args:
            airspeed: Airspeed in knots.
        """
        if not self._audio_engine or self._wind_source_id is None:
            return

        # Map airspeed to volume (0 at 0 knots, 1.0 at 100+ knots)
        volume = min(airspeed / 100.0, 1.0)
        # Map airspeed to pitch (0.8 at low speed, 1.5 at high speed)
        pitch = 0.8 + (min(airspeed / 200.0, 1.0) * 0.7)

        self._audio_engine.update_source_volume(self._wind_source_id, volume)
        self._audio_engine.update_source_pitch(self._wind_source_id, pitch)

    def play_gear_sound(self, gear_down: bool) -> None:
        """Play gear up/down sound.

        Args:
            gear_down: True for gear down, False for gear up.
        """
        if gear_down:
            path = str(get_resource_path("assets/sounds/aircraft/geardown1.mp3"))
        else:
            path = str(get_resource_path("assets/sounds/aircraft/gearup1.mp3"))

        try:
            self.play_sound_2d(path, volume=0.8)
        except FileNotFoundError:
            logger.warning(f"Gear sound not found: {path}")

    def play_flaps_sound(self, extending: bool) -> None:
        """Play flaps sound.

        Args:
            extending: True for extending, False for retracting.
        """
        if extending:
            path = str(get_resource_path("assets/sounds/aircraft/flapson1.mp3"))
        else:
            path = str(get_resource_path("assets/sounds/aircraft/flapsoff1.mp3"))

        try:
            self.play_sound_2d(path, volume=0.6)
        except FileNotFoundError:
            logger.warning(f"Flaps sound not found: {path}")

    def play_brakes_sound(self, brakes_on: bool) -> None:
        """Play brakes sound.

        Args:
            brakes_on: True for brakes on, False for brakes off.
        """
        if brakes_on:
            path = str(get_resource_path("assets/sounds/aircraft/brakeson.mp3"))
        else:
            path = str(get_resource_path("assets/sounds/aircraft/brakesoff.mp3"))

        try:
            self.play_sound_2d(path, volume=0.7)
        except FileNotFoundError:
            logger.warning(f"Brakes sound not found: {path}")

    def play_switch_sound(self, switch_on: bool) -> None:
        """Play switch click sound.

        Args:
            switch_on: True for switch on, False for switch off.
        """
        if switch_on:
            path = str(get_resource_path("assets/sounds/aircraft/switch_on.wav"))
        else:
            path = str(get_resource_path("assets/sounds/aircraft/switch_off.wav"))

        try:
            self.play_sound_2d(path, volume=0.5)
        except FileNotFoundError:
            logger.warning(f"Switch sound not found: {path}")

    def play_button_sound(self) -> None:
        """Play button press sound."""
        path = str(get_resource_path("assets/sounds/aircraft/button_press.wav"))

        try:
            self.play_sound_2d(path, volume=0.5)
        except FileNotFoundError:
            logger.warning(f"Button sound not found: {path}")

    def play_knob_sound(self) -> None:
        """Play knob turn sound."""
        path = str(get_resource_path("assets/sounds/aircraft/knob_turn.wav"))

        try:
            self.play_sound_2d(path, volume=0.4)
        except FileNotFoundError:
            logger.warning(f"Knob sound not found: {path}")

    def play_battery_sound(self, battery_on: bool, on_complete_callback: Any = None) -> None:
        """Play battery activation/deactivation sound sequence.

        For battery ON:
        1. Plays battery_on sound (one-shot startup sound)
        2. When it finishes, starts battery_loop sound (looping hum)
        3. Calls on_complete_callback when loop starts (battery truly ON)

        For battery OFF:
        1. Stops battery loop if playing
        2. Plays battery_off sound (shutdown sound)

        Sound paths must be configured via set_battery_sound_paths() first.

        Args:
            battery_on: True for battery on, False for battery off.
            on_complete_callback: Optional callback when battery is fully on (loop starts).
        """
        if not self._audio_engine:
            return

        if battery_on:
            # Stop any existing battery sounds
            if self._battery_loop_source_id is not None:
                self._audio_engine.stop_source(self._battery_loop_source_id)
                self._battery_loop_source_id = None

            if self._battery_on_source_id is not None:
                self._audio_engine.stop_source(self._battery_on_source_id)
                self._battery_on_source_id = None

            # Play battery on sound (one-shot)
            if self._battery_on_path:
                try:
                    path = str(get_resource_path(self._battery_on_path))
                    self._battery_on_source_id = self.play_sound_2d(path, volume=0.6)
                    self._battery_sequence_active = True
                    self._battery_sequence_callback = on_complete_callback
                    logger.info(f"Battery startup sound started ({self._battery_on_path})")
                except FileNotFoundError:
                    logger.warning(f"Battery startup sound not found: {self._battery_on_path}")
                    # Call callback immediately if sound not found
                    if on_complete_callback:
                        on_complete_callback()
            else:
                # No sound configured, call callback immediately
                if on_complete_callback:
                    on_complete_callback()
        else:
            # Battery turning OFF
            # Stop battery loop
            if self._battery_loop_source_id is not None:
                self._audio_engine.stop_source(self._battery_loop_source_id)
                self._battery_loop_source_id = None
                logger.info("Battery loop stopped")

            # Stop any startup sound
            if self._battery_on_source_id is not None:
                self._audio_engine.stop_source(self._battery_on_source_id)
                self._battery_on_source_id = None

            self._battery_sequence_active = False
            self._battery_sequence_callback = None

            # Play battery off sound
            if self._battery_off_path:
                try:
                    path = str(get_resource_path(self._battery_off_path))
                    self.play_sound_2d(path, volume=0.6)
                    logger.info(f"Battery shutdown sound played ({self._battery_off_path})")
                except FileNotFoundError:
                    logger.warning(f"Battery shutdown sound not found: {self._battery_off_path}")

    def start_rolling_sound(self, path: str | None = None) -> None:
        """Start looping base rolling/tire sound.

        Args:
            path: Path to rolling sound file (default: data/sounds/environment/ground_roll.wav).
        """
        if path is None:
            path = str(get_resource_path("data/sounds/environment/ground_roll.wav"))

        if not self._audio_engine:
            return

        from airborne.audio.engine.base import SourceState

        # Check if rolling sound is still playing (might have stopped despite loop=True)
        if hasattr(self, "_rolling_source_id") and self._rolling_source_id is not None:
            state = self._audio_engine.get_source_state(self._rolling_source_id)
            if state == SourceState.PLAYING:
                return  # Still playing, no need to restart

            # Sound stopped, clear the ID so we restart it
            self._rolling_source_id = None

        # Start new looping rolling sound at low volume/pitch (controlled by ground speed)
        try:
            self._rolling_source_id = self.play_sound_2d(path, volume=0.05, pitch=0.4, loop=True)
            logger.debug("Rolling sound started")
        except FileNotFoundError:
            logger.warning(f"Rolling sound not found: {path}")

    def _start_surface_sound(self, surface_type: str) -> None:
        """Start looping surface texture sound.

        Args:
            surface_type: Surface type (concrete, grass, gravel, asphalt, etc.)
        """
        if not self._audio_engine:
            return

        from airborne.audio.engine.base import SourceState

        # Initialize surface sound tracking if needed
        if not hasattr(self, "_surface_source_id"):
            self._surface_source_id: int | None = None
            self._current_surface_type: str | None = None

        # Map surface types to sound files
        surface_sound_map = {
            "concrete": "data/sounds/environment/concrete.wav",
            "asphalt": "data/sounds/environment/concrete.wav",  # Use concrete for asphalt
            "grass": "data/sounds/environment/grass.wav",
            "turf": "data/sounds/environment/grass.wav",  # Use grass for turf
            "gravel": "data/sounds/environment/gravel.wav",
            "dirt": "data/sounds/environment/gravel.wav",  # Use gravel for dirt
        }

        # Get sound path for surface type, default to concrete
        sound_file = surface_sound_map.get(
            surface_type.lower(), "data/sounds/environment/concrete.wav"
        )

        # Check if surface sound is still playing (might have stopped despite loop=True)
        sound_still_playing = False
        if self._surface_source_id is not None:
            state = self._audio_engine.get_source_state(self._surface_source_id)
            sound_still_playing = state == SourceState.PLAYING

        # If surface hasn't changed and sound is still playing, don't restart
        if self._current_surface_type == surface_type and sound_still_playing:
            return

        # Stop existing surface sound if switching surfaces or restarting
        if self._surface_source_id is not None:
            self._audio_engine.stop_source(self._surface_source_id)
            self._surface_source_id = None

        # Start new surface texture sound
        try:
            path = str(get_resource_path(sound_file))
            self._surface_source_id = self.play_sound_2d(path, volume=0.03, pitch=1.0, loop=True)
            self._current_surface_type = surface_type
            logger.debug(f"Surface sound started: {surface_type}")
        except FileNotFoundError:
            logger.warning(f"Surface sound not found: {sound_file}")
            self._current_surface_type = None

    def _stop_surface_sound(self) -> None:
        """Stop surface texture sound."""
        if not self._audio_engine:
            return

        if hasattr(self, "_surface_source_id") and self._surface_source_id is not None:
            self._audio_engine.stop_source(self._surface_source_id)
            self._surface_source_id = None
            self._current_surface_type = None

    def update_rolling_sound(
        self, ground_speed: float, on_ground: bool, surface_type: str = "concrete"
    ) -> None:
        """Update rolling sound based on ground speed and surface type.

        Plays two layered sounds:
        1. Base ground_roll.wav - pitch varies from 0.8 to 2.0 with speed
        2. Surface texture sound (concrete/grass/gravel) - volume varies with speed

        Args:
            ground_speed: Ground speed in knots
            on_ground: Whether aircraft is on the ground
            surface_type: Surface type (concrete, grass, gravel, asphalt, etc.)
        """
        if not self._audio_engine:
            return

        if not hasattr(self, "_rolling_source_id"):
            self._rolling_source_id = None
        if not hasattr(self, "_surface_source_id"):
            self._surface_source_id = None
            self._current_surface_type = None

        # Start rolling sounds if on ground and moving
        is_moving = ground_speed > 0.5  # Threshold for "moving"

        if on_ground and is_moving:
            # Start base rolling sound if not playing
            if self._rolling_source_id is None:
                self.start_rolling_sound()

            # Start/switch surface sound
            self._start_surface_sound(surface_type)
        elif not on_ground or not is_moving:
            # Stop all rolling sounds if airborne or stationary
            if self._rolling_source_id is not None:
                self._audio_engine.stop_source(self._rolling_source_id)
                self._rolling_source_id = None
            self._stop_surface_sound()
            return

        # Update volume and pitch based on ground speed
        # Speed normalization: 0 knots = 0.0, 55 knots (rotation speed) = 1.0
        speed_factor = min(ground_speed / 55.0, 1.0)

        # Base rolling sound: pitch 0.4-1.0, volume 0.05-0.5
        if self._rolling_source_id is not None:
            # Pitch: 0.4 at low speed, 1.0 at rotation speed (55+ knots)
            roll_pitch = 0.4 + (speed_factor * 0.6)
            # Volume: 0.05 at first motion, 0.5 at rotation speed
            roll_volume = 0.05 + (speed_factor * 0.45)

            self._audio_engine.update_source_pitch(self._rolling_source_id, roll_pitch)
            self._audio_engine.update_source_volume(self._rolling_source_id, roll_volume)

        # Surface texture sound: pitch 1.0 (fixed), volume 0.03-0.3
        if self._surface_source_id is not None:
            # Surface sound volume increases with speed (quieter than base roll)
            surface_volume = 0.03 + (speed_factor * 0.27)
            self._audio_engine.update_source_volume(self._surface_source_id, surface_volume)

    def update(self) -> None:
        """Update sound manager state.

        Should be called each frame to:
        - Update audio engine
        - Monitor engine sound sequence
        - Monitor battery sound sequence
        - Clean up finished sounds
        """
        if not self._audio_engine:
            return

        # Update audio engine
        self._audio_engine.update()

        # Check engine sound sequence (start -> idle transition)
        if self._engine_sequence_active and self._engine_start_source_id is not None:
            # Check if engine start sound has finished
            from airborne.audio.engine.base import SourceState

            state = self._audio_engine.get_source_state(self._engine_start_source_id)
            if state == SourceState.STOPPED:
                # Start sound finished, transition to idle
                logger.info("Engine start sound finished, starting idle sound")
                self._start_engine_idle()

        # Check battery sound sequence
        if self._battery_sequence_active and self._battery_on_source_id is not None:
            # Check if battery on sound has finished
            from airborne.audio.engine.base import SourceState

            state = self._audio_engine.get_source_state(self._battery_on_source_id)
            if state == SourceState.STOPPED:
                # Battery on sound finished, start the loop
                logger.info("Battery startup sound finished, starting loop")
                self._battery_on_source_id = None

                # Start battery loop sound
                if self._battery_loop_path:
                    try:
                        # Load with loop mode enabled
                        loop_sound = self._audio_engine.load_sound(
                            str(get_resource_path(self._battery_loop_path)),
                            preload=True,
                            loop_mode=True,
                        )
                        self._battery_loop_source_id = self._audio_engine.play_2d(
                            loop_sound, volume=0.5, pitch=1.0, loop=True
                        )
                        logger.info(f"Battery loop started ({self._battery_loop_path})")

                        # Battery is now truly ON - call callback
                        if self._battery_sequence_callback:
                            logger.info("Battery sequence complete - calling callback")
                            self._battery_sequence_callback()
                            self._battery_sequence_callback = None

                    except FileNotFoundError:
                        logger.warning(f"Battery loop sound not found: {self._battery_loop_path}")
                        # Still call callback even if sound not found
                        if self._battery_sequence_callback:
                            self._battery_sequence_callback()
                            self._battery_sequence_callback = None
                else:
                    # No loop sound configured, just call callback
                    if self._battery_sequence_callback:
                        self._battery_sequence_callback()
                        self._battery_sequence_callback = None

                self._battery_sequence_active = False

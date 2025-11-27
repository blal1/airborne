"""Audio plugin for the AirBorne flight simulator.

This plugin wraps the audio system (engine and TTS) as a plugin component,
making it available to other plugins through the plugin context.

Typical usage:
    The audio plugin is loaded automatically by the plugin loader and provides
    audio services to other plugins via the component registry.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from airborne.core.input import InputActionEvent

from airborne.audio.engine.base import IAudioEngine, Vector3
from airborne.audio.sound_manager import SoundManager
from airborne.audio.tts.base import ITTSProvider
from airborne.audio.tts.speech_messages import SpeechMessages
from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.core.resource_path import get_data_path, get_resource_path

logger = get_logger(__name__)

# Try to import audio engines, prioritizing FMOD
AUDIO_ENGINE_AVAILABLE = False
FMODEngine: type | None = None

# Loads FMOD
try:
    from airborne.audio.engine.fmod_engine import FMODEngine

    AUDIO_ENGINE_AVAILABLE = True
    logger.info("FMODEngine available")
except (ImportError, OSError) as e:
    logger.info(f"FMODEngine not available: {e}.")


class AudioPlugin(IPlugin):
    """Audio plugin that manages audio engine and TTS.

    This plugin wraps the sound manager, audio engine, and TTS provider,
    making them available to other plugins. It subscribes to position
    updates to maintain the 3D audio listener position.

    The plugin provides:
    - audio_engine: IAudioEngine instance
    - sound_manager: SoundManager instance
    """

    def __init__(self) -> None:
        """Initialize audio plugin."""
        self.context: PluginContext | None = None
        self.sound_manager: SoundManager | None = None
        self.audio_engine: IAudioEngine | None = None
        self.tts_provider: ITTSProvider | None = None
        self.atc_audio_manager: Any = None  # ATCAudioManager for radio communications

        # Listener state
        self._listener_position = Vector3(0.0, 0.0, 0.0)
        self._listener_forward = Vector3(0.0, 0.0, 1.0)
        self._listener_up = Vector3(0.0, 1.0, 0.0)
        self._listener_velocity = Vector3(0.0, 0.0, 0.0)

        # Aircraft state tracking for sounds
        self._last_gear_state = 1.0  # Start with gear down
        self._last_flaps_state = 0.0
        self._last_brakes_state = 0.0
        self._engine_sound_active = False  # Whether engine sound is currently playing
        self._last_engine_rpm = 0.0  # Track RPM for wind-down
        self._last_master_switch: bool | None = None  # Track battery state changes
        self._master_switch_initialized = False  # Track if we've received first message

        # High-frequency audio update timer
        self._audio_update_accumulator = 0.0
        self._audio_update_interval = 0.005  # Update audio every 5ms (200Hz) for smooth transitions

        # Aircraft configuration
        self._fixed_gear = False  # Will be updated during initialize

        # Flight state for instrument readouts
        self._airspeed = 0.0  # knots
        self._groundspeed = 0.0  # knots
        self._altitude = 0.0  # feet
        self._heading = 0.0  # degrees
        self._vspeed = 0.0  # feet per minute
        self._bank = 0.0  # degrees
        self._pitch = 0.0  # degrees

        # Engine state for instrument readouts
        self._engine_rpm = 0.0
        self._manifold_pressure = 0.0  # inches Hg
        self._oil_pressure = 0.0  # PSI
        self._oil_temp = 0.0  # Celsius
        self._fuel_flow = 0.0  # GPH
        self._engine_running = False

        # Electrical state for instrument readouts
        self._battery_voltage = 0.0  # Volts
        self._battery_percent = 0.0  # 0-100%
        self._battery_current = 0.0  # Amps (positive = charging, negative = discharging)
        self._alternator_output = 0.0  # Amps

        # Fuel state for instrument readouts
        self._fuel_quantity = 0.0  # Gallons
        self._fuel_remaining_minutes = 0.0  # Minutes

        # Stall warning state
        self._angle_of_attack = 0.0  # degrees
        self._stall_warning_active = False
        self._stall_warning_sound: Any = None  # Sound object
        self._stall_warning_source_id: int | None = None  # Source ID for stopping
        self._stall_announced = False  # Track if we've announced "Stall!" for current stall event
        self._stall_warn_aoa_threshold = 14.0  # Start warning at 14° AOA
        self._stall_aoa_threshold = 16.0  # Full stall at 16° AOA

        # Trim state for readouts
        self._pitch_trim = 0.0  # -1.0 to 1.0 (0.0 = neutral)
        self._rudder_trim = 0.0  # -1.0 to 1.0 (0.0 = neutral)

        # Pitch control feedback - continuous sweeping tone
        self._last_pitch_control = 0.0  # Track pitch control position
        self._pitch_tone_channel: int | None = None  # Currently playing tone
        self._pitch_tone_active = False  # Whether tone is currently playing
        self._last_pitch_freq = 440.0  # Last frequency played (for change detection)

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing this audio plugin.
        """
        return PluginMetadata(
            name="audio_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.CORE,
            dependencies=[],
            provides=["audio_engine", "sound_manager", "tts"],
            optional=False,
            update_priority=100,  # Update late (after physics)
            requires_physics=False,
            description="Audio system plugin with 3D audio and TTS",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the audio plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Get aircraft config (for fixed_gear, etc.)
        aircraft_config = context.config.get("aircraft", {})
        self._fixed_gear = aircraft_config.get("fixed_gear", False)
        logger.info(f"AudioPlugin: fixed_gear={self._fixed_gear}")

        # Get audio config from context
        audio_config = context.config.get("audio", {})
        tts_config = context.config.get("tts", {})

        # Create audio engine and TTS provider
        if AUDIO_ENGINE_AVAILABLE:
            try:
                # Initialize FMOD
                if FMODEngine is not None:
                    self.audio_engine = FMODEngine()
                    logger.info("FMODEngine created successfully")
                else:
                    self.audio_engine = None
            except Exception as e:
                logger.error(f"Failed to create audio engine: {e}")
                self.audio_engine = None
        else:
            logger.error("Audio engine not available, running without audio")
            self.audio_engine = None

        # Create audio speech provider only if audio engine is available
        if self.audio_engine:
            from airborne.audio.tts.audio_provider import AudioSpeechProvider

            self.tts_provider = AudioSpeechProvider()
            # Pass audio engine reference and resource paths to TTS provider
            tts_config["audio_engine"] = self.audio_engine
            tts_config["speech_dir"] = str(get_data_path("speech"))
            tts_config["config_dir"] = str(get_resource_path("config"))
            self.tts_provider.initialize(tts_config)
        else:
            logger.error("TTS provider disabled due to missing audio engine")
            self.tts_provider = None

        # Create sound manager only if audio engine is available
        if self.audio_engine and self.tts_provider:
            self.sound_manager = SoundManager()
            # Don't pass tts_config again - TTS is already initialized
            self.sound_manager.initialize(
                audio_engine=self.audio_engine,
                tts_provider=self.tts_provider,
                audio_config=audio_config,
                tts_config=None,  # Already initialized above
            )
        else:
            logger.error("Sound manager disabled due to missing audio engine or TTS")
            self.sound_manager = None

        # Create ATC audio manager for radio communications
        if self.audio_engine:
            try:
                from airborne.audio.atc.atc_audio import ATCAudioManager

                config_dir = get_resource_path("config")
                speech_dir = get_data_path("speech/en")  # ATC uses same speech dir for now
                self.atc_audio_manager = ATCAudioManager(self.audio_engine, config_dir, speech_dir)
                # Wire up TTS provider for system TTS fallback
                if self.tts_provider:
                    self.atc_audio_manager.set_tts_provider(self.tts_provider)
                logger.info("ATC audio manager initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize ATC audio manager: {e}")
                self.atc_audio_manager = None
        else:
            self.atc_audio_manager = None

        # Register components in registry
        if context.plugin_registry:
            if self.audio_engine:
                context.plugin_registry.register("audio_engine", self.audio_engine)
            if self.sound_manager:
                context.plugin_registry.register("sound_manager", self.sound_manager)
            context.plugin_registry.register("tts", self.tts_provider)

        # Subscribe to position updates, TTS requests, control inputs, and system states
        context.message_queue.subscribe(MessageTopic.POSITION_UPDATED, self.handle_message)
        context.message_queue.subscribe(MessageTopic.TTS_SPEAK, self.handle_message)
        context.message_queue.subscribe(MessageTopic.TTS_INTERRUPT, self.handle_message)
        context.message_queue.subscribe(MessageTopic.PROXIMITY_BEEP, self.handle_message)
        context.message_queue.subscribe(MessageTopic.CONTROL_INPUT, self.handle_message)
        context.message_queue.subscribe(MessageTopic.ENGINE_STATE, self.handle_message)
        context.message_queue.subscribe(MessageTopic.SYSTEM_STATE, self.handle_message)

        # Subscribe to electrical panel control messages for battery sounds
        context.message_queue.subscribe("electrical.master_switch", self.handle_message)

        # Subscribe to click sound messages from panel controls
        context.message_queue.subscribe("audio.play_click", self.handle_message)

        # Subscribe to input action events from event bus for TTS feedback
        if context.event_bus:
            from airborne.core.input import InputActionEvent

            context.event_bus.subscribe(InputActionEvent, self._handle_input_action)

        # Configure engine sound pitch range from aircraft config
        if self.sound_manager:
            aircraft_audio = audio_config.get("aircraft", {})
            engine_sounds = aircraft_audio.get("engine_sounds", {})
            if engine_sounds:
                pitch_idle = engine_sounds.get("pitch_idle", 0.7)
                pitch_full = engine_sounds.get("pitch_full", 1.3)
                self.sound_manager.set_engine_pitch_range(pitch_idle, pitch_full)
                logger.info(f"Engine pitch range configured: {pitch_idle} to {pitch_full}")

                # Check if we have start/idle/shutdown sound structure (new format)
                if "start" in engine_sounds and "idle" in engine_sounds:
                    # New format: start/idle/shutdown sequence
                    start_path = str(get_resource_path(engine_sounds.get("start")))
                    idle_path = str(get_resource_path(engine_sounds.get("idle")))
                    shutdown_path = (
                        str(get_resource_path(engine_sounds.get("shutdown", "")))
                        if "shutdown" in engine_sounds
                        else None
                    )

                    self.sound_manager.set_engine_sound_paths(start_path, idle_path, shutdown_path)
                    self._engine_sound_path = idle_path  # Store idle path for compatibility
                    logger.info(
                        f"Engine sound sequence configured: start={start_path}, idle={idle_path}, shutdown={shutdown_path}"
                    )
                else:
                    # Old format: single running sound
                    engine_sound_relative = engine_sounds.get(
                        "running", "assets/sounds/aircraft/engine.wav"
                    )
                    self._engine_sound_path = str(get_resource_path(engine_sound_relative))
                    logger.info(f"Engine sound configured: {self._engine_sound_path}")
            else:
                self._engine_sound_path = str(
                    get_resource_path("assets/sounds/aircraft/engine.wav")
                )

            self.sound_manager.start_wind_sound()
            self._engine_sound_active = False  # Engine sound starts off
            self._last_engine_rpm = 0.0

        logger.info("Audio plugin initialized")

    def update(self, dt: float) -> None:
        """Update audio systems.

        Args:
            dt: Delta time in seconds since last update.
        """
        if not self.sound_manager:
            return

        # Accumulate time for high-frequency audio updates
        self._audio_update_accumulator += dt

        # Update audio at high frequency (every 5ms / 200Hz) for smooth sound transitions
        while self._audio_update_accumulator >= self._audio_update_interval:
            self.sound_manager.update()
            self._audio_update_accumulator -= self._audio_update_interval

        # Update TTS sequential playback (once per frame is fine)
        if self.tts_provider and hasattr(self.tts_provider, "update"):
            self.tts_provider.update()

        # NOTE: Stall warning disabled - not working correctly with current AOA values
        # self._update_stall_warning()

        # Update listener position (once per frame is fine)
        self.sound_manager.update_listener(
            position=self._listener_position,
            forward=self._listener_forward,
            up=self._listener_up,
            velocity=self._listener_velocity,
        )

    def _update_stall_warning(self) -> None:
        """Update stall warning sound based on angle of attack."""
        if not self.audio_engine:
            return

        aoa = abs(self._angle_of_attack)  # Use absolute value for both positive and negative AOA

        # Determine if we should play stall warning
        should_warn = aoa >= self._stall_warn_aoa_threshold
        is_stalling = aoa >= self._stall_aoa_threshold

        # Start/stop stall warning sound (looping)
        if should_warn and not self._stall_warning_active:
            # Start playing stall warning sound (looping)
            logger.info(f"Stall warning activated (AOA={aoa:.1f}°)")
            sound_path = str(get_resource_path("assets/sounds/aircraft/stall_warn.mp3"))
            try:
                self._stall_warning_sound = self.audio_engine.load_sound(sound_path)
                if self._stall_warning_sound is not None:
                    self._stall_warning_source_id = self.audio_engine.play_2d(
                        self._stall_warning_sound, loop=True, volume=0.7
                    )
                    self._stall_warning_active = True
            except Exception as e:
                logger.error(f"Failed to play stall warning sound: {e}")

        elif not should_warn and self._stall_warning_active:
            # Stop playing stall warning sound
            logger.info(f"Stall warning deactivated (AOA={aoa:.1f}°)")
            if self._stall_warning_source_id is not None:
                self.audio_engine.stop_source(self._stall_warning_source_id)
                self._stall_warning_source_id = None
            self._stall_warning_active = False
            self._stall_announced = False  # Reset announcement flag when exiting stall

        # Announce "Stall!" once when entering full stall
        if is_stalling and not self._stall_announced and self.tts_provider:
            logger.info(f"STALL! (AOA={aoa:.1f}°)")
            # Play "Stall!" message with high priority, interrupting other speech
            from airborne.audio.tts.base import TTSPriority

            stall_message = ["MSG_WORD_STALL", "MSG_WORD_STALL"]  # "Stall! Stall!"
            self.tts_provider.speak(stall_message, priority=TTSPriority.CRITICAL, interrupt=True)
            self._stall_announced = True

    def _update_pitch_feedback_tone(self, pitch: float) -> None:
        """Update sweeping tone to indicate pitch control position.

        Uses rapid short beeps that change frequency, creating a sweeping effect:
        - pitch = 0.0 (neutral): SILENT (no tone)
        - pitch = +0.05 to +1.0 (forward/nose down): 330-220 Hz (falling sweep)
        - pitch = -0.05 to -1.0 (back/nose up): 550-880 Hz (rising sweep)

        Args:
            pitch: Pitch control position (-1.0 to 1.0).
        """
        if not self.audio_engine:
            return

        # Threshold for silence (dead zone around neutral)
        silence_threshold = 0.05

        # If pitch is near neutral, stop any active tone
        if abs(pitch) < silence_threshold:
            if self._pitch_tone_active:
                if self._pitch_tone_channel is not None:
                    from contextlib import suppress

                    with suppress(Exception):
                        self.audio_engine.stop_source(self._pitch_tone_channel)
                    self._pitch_tone_channel = None
                self._pitch_tone_active = False
                self._last_pitch_freq = 440.0
            return

        # Calculate frequency based on pitch position
        # Base frequency is 440 Hz (A4)
        # Range: 220 Hz (pitch = +1.0) to 880 Hz (pitch = -1.0)
        base_freq = 440.0
        # Map pitch from [-1.0, 1.0] to frequency [880, 220]
        # Higher pitch (nose up) = higher frequency
        freq = base_freq * (2.0 ** (-pitch))  # Exponential mapping for musical scale

        # Only update if frequency changed significantly (creates sweeping effect)
        freq_change_threshold = 10.0  # Hz
        if abs(freq - self._last_pitch_freq) < freq_change_threshold:
            return  # No significant change, don't restart beep

        self._last_pitch_freq = freq

        # Stop previous beep
        if self._pitch_tone_channel is not None:
            from contextlib import suppress

            with suppress(Exception):
                self.audio_engine.stop_source(self._pitch_tone_channel)
            self._pitch_tone_channel = None

        # Generate and play new beep at current frequency
        import tempfile
        import wave

        import numpy as np

        # Generate short beep (100ms for rapid updates)
        sample_rate = 44100
        duration = 0.1  # 100ms beep
        samples = int(sample_rate * duration)

        # Create sine wave at current frequency
        t = np.linspace(0, duration, samples, False)
        tone = np.sin(2 * np.pi * freq * t)

        # Apply envelope (fade in/out to avoid clicks)
        fade_samples = int(sample_rate * 0.01)  # 10ms fade
        fade_in = np.linspace(0, 1, fade_samples)
        fade_out = np.linspace(1, 0, fade_samples)
        tone[:fade_samples] *= fade_in
        tone[-fade_samples:] *= fade_out

        # Convert to float32
        tone = tone.astype(np.float32) * 0.25  # Volume

        try:
            # Create temporary WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                temp_path = temp_wav.name

            # Write WAV file
            with wave.open(temp_path, "wb") as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                tone_int16 = (tone * 32767).astype(np.int16)
                wav_file.writeframes(tone_int16.tobytes())

            # Load and play the sound (non-looping)
            sound = self.audio_engine.load_sound(temp_path)
            if sound is not None:
                self._pitch_tone_channel = self.audio_engine.play_2d(sound, loop=False, volume=0.5)
                self._pitch_tone_active = True
                logger.debug(f"Pitch sweep: {freq:.1f} Hz (pitch={pitch:.2f})")

            # Clean up temp file
            import os
            from contextlib import suppress

            with suppress(Exception):
                os.unlink(temp_path)

        except Exception as e:
            logger.warning(f"Failed to play pitch sweep tone: {e}")

    def shutdown(self) -> None:
        """Shutdown the audio plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe(
                MessageTopic.POSITION_UPDATED, self.handle_message
            )
            self.context.message_queue.unsubscribe(MessageTopic.TTS_SPEAK, self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.TTS_INTERRUPT, self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.PROXIMITY_BEEP, self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.CONTROL_INPUT, self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.ENGINE_STATE, self.handle_message)
            self.context.message_queue.unsubscribe(MessageTopic.SYSTEM_STATE, self.handle_message)
            self.context.message_queue.unsubscribe("electrical.master_switch", self.handle_message)
            self.context.message_queue.unsubscribe("audio.play_click", self.handle_message)

            # Unregister components (only if they were registered)
            if self.context.plugin_registry:
                if self.audio_engine:
                    self.context.plugin_registry.unregister("audio_engine")
                if self.sound_manager:
                    self.context.plugin_registry.unregister("sound_manager")
                self.context.plugin_registry.unregister("tts")

        # Shutdown sound manager (which shutdowns engine and TTS)
        if self.sound_manager:
            self.sound_manager.shutdown()

        logger.info("Audio plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins.

        Args:
            message: Message from the queue.
        """
        if message.topic == MessageTopic.CONTROL_INPUT:
            # Handle control input changes for sound effects
            data = message.data

            # Gear change (skip for fixed gear aircraft)
            if "gear" in data and self.sound_manager and not self._fixed_gear:
                gear = data["gear"]
                if gear != self._last_gear_state:
                    self.sound_manager.play_gear_sound(gear > 0.5)
                    self._last_gear_state = gear

            # Flaps change
            if "flaps" in data and self.sound_manager:
                flaps = data["flaps"]
                if flaps != self._last_flaps_state:
                    extending = flaps > self._last_flaps_state
                    self.sound_manager.play_flaps_sound(extending)
                    self._last_flaps_state = flaps

            # Brakes change
            if "brakes" in data and self.sound_manager:
                brakes = data["brakes"]
                if brakes != self._last_brakes_state:
                    self.sound_manager.play_brakes_sound(brakes > 0.0)
                    self._last_brakes_state = brakes

            # Pitch control feedback with continuous tone
            # Tone plays continuously while yoke is deflected, stops at neutral
            if "pitch" in data and self.audio_engine:
                pitch = data["pitch"]
                # Update tone frequency to match current pitch position
                # Tone starts when pitch moves away from neutral, stops when returning to neutral
                self._update_pitch_feedback_tone(pitch)
                self._last_pitch_control = pitch

            # Note: Engine sound is now updated by RPM in ENGINE_STATE handler, not throttle

        elif message.topic == MessageTopic.TTS_SPEAK:
            # Handle TTS speak requests
            if self.tts_provider:
                text = message.data.get("text", "")
                priority_str = message.data.get("priority", "normal")

                # Map priority string to TTSPriority enum
                from airborne.audio.tts.base import TTSPriority

                priority_map = {
                    "low": TTSPriority.LOW,
                    "normal": TTSPriority.NORMAL,
                    "high": TTSPriority.HIGH,
                    "critical": TTSPriority.CRITICAL,
                }
                priority = priority_map.get(priority_str.lower(), TTSPriority.NORMAL)

                interrupt = message.data.get("interrupt", False)

                logger.debug(f"TTS request: '{text}' (priority={priority.name})")
                self.tts_provider.speak(text, priority=priority, interrupt=interrupt)

        elif message.topic == MessageTopic.TTS_INTERRUPT:
            # Handle TTS interrupt (stop current speech)
            if self.tts_provider:
                logger.debug("TTS interrupt requested")
                self.tts_provider.stop()

        elif message.topic == MessageTopic.PROXIMITY_BEEP:
            # Handle proximity beep requests from ground navigation
            if self.audio_engine:
                import numpy as np

                data = message.data
                samples = np.array(data.get("samples", []), dtype=np.float32)
                _ = data.get("sample_rate", 44100)  # For future use

                if len(samples) > 0:
                    # Play raw audio samples through audio engine
                    # For now, we log the beep info. Full implementation would call
                    # audio_engine.play_raw_samples(samples, sample_rate)
                    target_id = data.get("target_id", "unknown")
                    distance = data.get("distance", 0.0)
                    frequency = data.get("frequency", 0.0)
                    logger.debug(
                        "Playing proximity beep: target=%s, distance=%.1fm, freq=%.2fHz, samples=%d",
                        target_id,
                        distance,
                        frequency,
                        len(samples),
                    )
                    # TODO: Implement play_raw_samples() in audio engines
                    # self.audio_engine.play_raw_samples(samples, sample_rate)

        elif message.topic == MessageTopic.POSITION_UPDATED:
            # Update listener position from aircraft position
            data = message.data

            # Update flight state for instrument readouts
            if "airspeed" in data:
                self._airspeed = data["airspeed"]
            if "groundspeed" in data:
                self._groundspeed = data["groundspeed"]
            if "altitude" in data:
                self._altitude = data["altitude"]
            if "heading" in data:
                self._heading = data["heading"]
            if "vspeed" in data:
                self._vspeed = data["vspeed"]
            if "bank" in data:
                self._bank = data["bank"]
            if "pitch" in data:
                self._pitch = data["pitch"]
            if "angle_of_attack_deg" in data:
                aoa_value = data["angle_of_attack_deg"]
                if aoa_value is not None:
                    self._angle_of_attack = aoa_value

            # Update wind sound based on airspeed
            if "airspeed" in data and self.sound_manager:
                airspeed = data["airspeed"]
                self.sound_manager.update_wind_sound(airspeed)

            # Update rolling sound based on ground speed and on_ground status
            if "groundspeed" in data and "on_ground" in data and self.sound_manager:
                ground_speed = data["groundspeed"]
                on_ground = data["on_ground"]
                self.sound_manager.update_rolling_sound(ground_speed, on_ground)

            if "position" in data:
                pos = data["position"]
                if isinstance(pos, dict):
                    self._listener_position = Vector3(
                        pos.get("x", 0.0), pos.get("y", 0.0), pos.get("z", 0.0)
                    )
                elif isinstance(pos, (tuple, list)) and len(pos) >= 3:
                    self._listener_position = Vector3(float(pos[0]), float(pos[1]), float(pos[2]))

            if "forward" in data:
                fwd = data["forward"]
                if isinstance(fwd, dict):
                    self._listener_forward = Vector3(
                        fwd.get("x", 0.0), fwd.get("y", 0.0), fwd.get("z", 1.0)
                    )
                elif isinstance(fwd, (tuple, list)) and len(fwd) >= 3:
                    self._listener_forward = Vector3(float(fwd[0]), float(fwd[1]), float(fwd[2]))

            if "up" in data:
                up = data["up"]
                if isinstance(up, dict):
                    self._listener_up = Vector3(
                        up.get("x", 0.0), up.get("y", 1.0), up.get("z", 0.0)
                    )
                elif isinstance(up, (tuple, list)) and len(up) >= 3:
                    self._listener_up = Vector3(float(up[0]), float(up[1]), float(up[2]))

            if "velocity" in data:
                vel = data["velocity"]
                if isinstance(vel, dict):
                    self._listener_velocity = Vector3(
                        vel.get("x", 0.0), vel.get("y", 0.0), vel.get("z", 0.0)
                    )
                elif isinstance(vel, (tuple, list)) and len(vel) >= 3:
                    self._listener_velocity = Vector3(float(vel[0]), float(vel[1]), float(vel[2]))

        elif message.topic == MessageTopic.ENGINE_STATE:
            # Update engine state for instrument readouts
            data = message.data
            engine_running = data.get("running", False)
            engine_rpm = data.get("rpm", 0.0)

            # Start/stop engine sound based on ENGINE RUNNING state
            # Only play engine sounds when the engine actually catches and runs
            # Do NOT play sounds just from starter cranking
            if self.sound_manager and hasattr(self, "_engine_sound_active"):
                if engine_running and not self._engine_sound_active:
                    # Engine started: Play start.wav -> idle.wav sequence
                    # Check if we have the new sound sequence configured
                    if (
                        hasattr(self.sound_manager, "_engine_start_path")
                        and self.sound_manager._engine_start_path
                    ):
                        # New format: use start_engine_sequence (start.wav -> idle.wav)
                        self.sound_manager.start_engine_sequence()
                        logger.info(
                            f"Engine started: sound sequence playing (RPM = {engine_rpm:.0f})"
                        )
                    else:
                        # Old format: use single engine sound
                        engine_sound_path = getattr(
                            self, "_engine_sound_path", "assets/sounds/aircraft/engine.wav"
                        )
                        self.sound_manager.start_engine_sound(engine_sound_path)
                        logger.info(f"Engine started: sound playing (RPM = {engine_rpm:.0f})")
                    self._engine_sound_active = True
                elif not engine_running and self._engine_sound_active:
                    # Engine stopped: Play shutdown.wav and stop idle loop
                    if hasattr(self.sound_manager, "stop_engine_sound"):
                        # New format: stop with shutdown.wav
                        self.sound_manager.stop_engine_sound(play_shutdown=True)
                        logger.info("Engine stopped: shutdown sound playing")
                    else:
                        # Old format: just stop the sound
                        if (
                            hasattr(self.sound_manager, "_engine_source_id")
                            and self.sound_manager._engine_source_id is not None
                        ):
                            self.sound_manager.stop_sound(self.sound_manager._engine_source_id)
                            self.sound_manager._engine_source_id = None
                        logger.info("Engine stopped: sound stopped")
                    self._engine_sound_active = False

                # Update engine sound pitch based on RPM
                if self._engine_sound_active and engine_rpm > 0:
                    # Get engine RPM limits from config or use defaults
                    max_rpm = 2700.0  # Cessna 172 max RPM
                    # Map RPM directly to throttle (0 RPM = 0.0, max RPM = 1.0)
                    # This works correctly for both cranking (low RPM) and running
                    throttle = max(0.0, min(1.0, engine_rpm / max_rpm))
                    self.sound_manager.update_engine_sound(throttle)
                    logger.debug(
                        f"Engine sound updated: {engine_rpm:.0f} RPM → throttle {throttle:.2f}"
                    )

            self._engine_running = engine_running
            self._engine_rpm = engine_rpm
            self._last_engine_rpm = engine_rpm  # Track for potential future use
            self._manifold_pressure = data.get("manifold_pressure", 0.0)
            self._oil_pressure = data.get("oil_pressure", 0.0)
            self._oil_temp = data.get("oil_temp", 0.0)
            self._fuel_flow = data.get("fuel_flow", 0.0)

        elif message.topic == MessageTopic.SYSTEM_STATE:
            # Update system states for instrument readouts
            data = message.data
            system = data.get("system")

            if system == "electrical":
                # Battery sounds are handled by electrical.master_switch messages from control panel
                # This handler only tracks electrical state for instrument readouts
                self._battery_voltage = data.get("battery_voltage", 0.0)
                self._battery_percent = data.get("battery_soc_percent", 0.0)
                self._battery_current = data.get("battery_current_amps", 0.0)
                self._alternator_output = data.get("alternator_output_amps", 0.0)

            elif system == "fuel":
                self._fuel_quantity = data.get("total_quantity_gallons", 0.0)
                self._fuel_remaining_minutes = data.get("time_remaining_minutes", 0.0)

        elif message.topic == "electrical.master_switch":
            # Handle master switch from control panel
            data = message.data
            state = data.get("state", "")

            # Handle both string ("ON"/"OFF") and boolean (True/False) formats
            if isinstance(state, bool):
                master_on = state
            elif isinstance(state, str):
                master_on = state == "ON"
            else:
                master_on = False

            logger.info(
                f"Received electrical.master_switch message: state={state} (type={type(state).__name__}), master_on={master_on}, last={self._last_master_switch}, initialized={self._master_switch_initialized}"
            )

            # Play battery sound when master switch changes
            # Skip ONLY if this is the very first message AND the state is already correct
            should_play = False
            if self.sound_manager:
                if not self._master_switch_initialized:
                    # First message - only skip if this is startup state (False/OFF)
                    # If it's ON, it means user pressed it, so play the sound
                    should_play = master_on  # Play only if turning ON
                    self._master_switch_initialized = True
                elif master_on != self._last_master_switch:
                    # Subsequent messages - play if state changed
                    should_play = True

            if should_play:
                if master_on:
                    # Turning ON - play sequence with callback
                    def on_battery_ready():
                        """Called when battery loop starts (battery is truly ON)."""
                        logger.info("Battery ready - activating electrical system")
                        # Send message to electrical system to actually turn on
                        if self.context:
                            self.context.message_queue.publish(
                                Message(
                                    sender="audio_plugin",
                                    recipients=["simple_electrical_system"],
                                    topic=MessageTopic.ELECTRICAL_STATE,
                                    data={"battery_master": True},
                                    priority=MessagePriority.HIGH,
                                )
                            )

                    self.sound_manager.play_battery_sound(
                        True, on_complete_callback=on_battery_ready
                    )
                    logger.info("Battery startup sequence initiated")
                else:
                    # Turning OFF - immediate
                    self.sound_manager.play_battery_sound(False)
                    logger.info("Battery shutdown (panel control)")

            # Always update the last state (even on first time)
            self._last_master_switch = master_on

        elif message.topic == "audio.play_click":
            # Handle click sound request from panel controls
            if self.sound_manager:
                control_type = message.data.get("control_type", "knob")

                # Use different click sounds for different control types
                if control_type == "switch":
                    sound_file = str(get_resource_path("assets/sounds/aircraft/click_switch.mp3"))
                else:  # knob or slider - both use knob click
                    sound_file = str(get_resource_path("assets/sounds/aircraft/click_knob.mp3"))

                self.sound_manager.play_sound_2d(sound_file, volume=0.8)

    def on_config_changed(self, config: dict[str, Any]) -> None:
        """Handle configuration changes.

        Args:
            config: New configuration dictionary.
        """
        # Update audio settings if changed
        audio_config = config.get("audio", {})

        if self.sound_manager and "master_volume" in audio_config:
            self.sound_manager.set_master_volume(audio_config["master_volume"])

        if self.sound_manager and "tts_enabled" in audio_config:
            self.sound_manager.set_tts_enabled(audio_config["tts_enabled"])

        if self.tts_provider:
            if "rate" in audio_config:
                self.tts_provider.set_rate(audio_config["rate"])
            if "volume" in audio_config:
                self.tts_provider.set_volume(audio_config["volume"])

        logger.info("Audio plugin configuration updated")

    def _handle_input_action(self, event: "InputActionEvent") -> None:
        """Handle input action events and provide TTS feedback.

        Args:
            event: Input action event from event bus.
        """
        logger.debug(f"Input action received: {event.action}")

        # Handle throttle click sound (no TTS needed)
        if event.action == "throttle_click":
            if self.sound_manager:
                self.sound_manager.play_sound_2d(
                    "assets/sounds/aircraft/click_knob.mp3", volume=0.3
                )
            return

        # Handle trim adjustment sound and TTS
        if event.action == "trim_pitch_adjusted":
            # Store trim value (convert from 0-100 percentage to -1.0 to 1.0 scale)
            if event.value is not None:
                trim_percent = int(event.value)
                self._pitch_trim = (trim_percent - 50) / 50.0  # 0->-1.0, 50->0.0, 100->1.0
            # Play click sound
            if self.sound_manager:
                self.sound_manager.play_sound_2d(
                    "assets/sounds/aircraft/click_knob.mp3", volume=0.3
                )
            # Announce trim position (HIGH priority + interrupt to stop previous announcements)
            if self.tts_provider and event.value is not None:
                trim_percent = int(event.value)
                message_keys = SpeechMessages.trim_position(trim_percent)
                from airborne.audio.tts.base import TTSPriority

                self.tts_provider.speak(message_keys, priority=TTSPriority.HIGH, interrupt=True)  # type: ignore[arg-type]
            return

        # Handle rudder trim adjustment sound and TTS
        if event.action == "trim_rudder_adjusted":
            # Store trim value (convert from 0-100 percentage to -1.0 to 1.0 scale)
            if event.value is not None:
                trim_percent = int(event.value)
                self._rudder_trim = (trim_percent - 50) / 50.0  # 0->-1.0, 50->0.0, 100->1.0
            # Play click sound
            if self.sound_manager:
                self.sound_manager.play_sound_2d(
                    "assets/sounds/aircraft/click_knob.mp3", volume=0.3
                )
            # Announce rudder trim position (HIGH priority + interrupt to stop previous announcements)
            if self.tts_provider and event.value is not None:
                trim_percent = int(event.value)
                message_keys = SpeechMessages.rudder_trim_position(trim_percent)
                from airborne.audio.tts.base import TTSPriority

                self.tts_provider.speak(message_keys, priority=TTSPriority.HIGH, interrupt=True)  # type: ignore[arg-type]
            return

        # Handle parking brake click sound (then continue to TTS)
        if event.action in ("parking_brake_set", "parking_brake_release") and self.sound_manager:
            sound_file = str(get_resource_path("assets/sounds/aircraft/click_switch.mp3"))
            self.sound_manager.play_sound_2d(sound_file, volume=0.8)

        # Handle throttle released (announce percent)
        if event.action == "throttle_released" and event.value is not None:
            if self.tts_provider:
                throttle_percent = int(event.value)
                keys = SpeechMessages.throttle_percent(throttle_percent)
                # Interrupt any current speech to announce throttle immediately
                self.tts_provider.speak(keys, interrupt=True)  # type: ignore[arg-type]
            return

        if not self.tts_provider:
            logger.warning("No TTS provider available for input action feedback")
            return

        message: str | None = None

        # Handle instrument readouts
        if event.action == "read_airspeed":
            import math

            airspeed_val = 0 if math.isnan(self._airspeed) else int(self._airspeed)
            message = f"{airspeed_val} knots"  # Removed "Airspeed" prefix
        elif event.action == "read_altitude":
            import math

            altitude_val = 0 if math.isnan(self._altitude) else int(self._altitude)
            message = f"{altitude_val} feet"  # Removed "Altitude" prefix
        elif event.action == "read_heading":
            import math

            heading_val = 0 if math.isnan(self._heading) else int(self._heading)
            message = f"Heading {heading_val} degrees"
        elif event.action == "read_vspeed":
            # Format vertical speed with sign (removed "Vertical speed" prefix)
            import math

            vspeed_int = 0 if math.isnan(self._vspeed) else int(self._vspeed)
            if vspeed_int > 0:
                message = f"Climbing {vspeed_int}"  # Removed "feet per minute"
            elif vspeed_int < 0:
                message = f"Descending {abs(vspeed_int)}"  # Removed "feet per minute"
            else:
                message = "Level"  # Removed "flight"
        elif event.action == "read_attitude":
            # Format bank and pitch angles
            bank_int = int(self._bank)
            pitch_int = int(self._pitch)
            bank_dir = "left" if bank_int < 0 else "right" if bank_int > 0 else "level"
            pitch_dir = "up" if pitch_int > 0 else "down" if pitch_int < 0 else "level"
            if bank_int == 0 and pitch_int == 0:
                message = "Level attitude"
            elif bank_int == 0:
                message = f"Pitch {abs(pitch_int)} degrees {pitch_dir}"
            elif pitch_int == 0:
                message = f"Bank {abs(bank_int)} degrees {bank_dir}"
            else:
                message = f"Bank {abs(bank_int)} {bank_dir}, pitch {abs(pitch_int)} {pitch_dir}"

        # Engine instrument readouts
        elif event.action == "read_rpm":
            if self._engine_running:
                message = f"Engine RPM {int(self._engine_rpm)}"
            else:
                message = "Engine stopped"
        elif event.action == "read_manifold_pressure":
            message = f"Manifold pressure {self._manifold_pressure:.1f} inches"
        elif event.action == "read_oil_pressure":
            message = f"Oil pressure {int(self._oil_pressure)} PSI"
        elif event.action == "read_oil_temp":
            # Convert Celsius to Fahrenheit for readout
            oil_temp_f = self._oil_temp * 9 / 5 + 32
            message = f"Oil temperature {int(oil_temp_f)} degrees"
        elif event.action == "read_fuel_flow":
            message = f"Fuel flow {self._fuel_flow:.1f} gallons per hour"

        # Electrical instrument readouts
        elif event.action == "read_battery_voltage":
            message = f"Battery {self._battery_voltage:.1f} volts"
        elif event.action == "read_battery_percent":
            message = f"Battery {int(self._battery_percent)} percent"
        elif event.action == "read_battery_status":
            if self._battery_current > 1.0:
                message = f"Battery charging at {self._battery_current:.1f} amps"
            elif self._battery_current < -1.0:
                message = f"Battery discharging at {abs(self._battery_current):.1f} amps"
            else:
                message = "Battery stable"
        elif event.action == "read_alternator":
            message = f"Alternator output {self._alternator_output:.1f} amps"

        # Fuel instrument readouts
        elif event.action == "read_fuel_quantity":
            message = f"Fuel quantity {self._fuel_quantity:.1f} gallons"
        elif event.action == "read_fuel_remaining":
            fuel_minutes = self._fuel_remaining_minutes or 0.0
            hours = int(fuel_minutes / 60)
            minutes = int(fuel_minutes % 60)
            if hours > 0:
                message = f"Fuel remaining {hours} hours {minutes} minutes"
            else:
                message = f"Fuel remaining {minutes} minutes"

        # Comprehensive status readouts (Alt+5, Alt+6, Alt+7)
        elif event.action == "read_engine":
            if self._engine_running:
                message = f"Engine {int(self._engine_rpm)} RPM"
            else:
                message = "Engine stopped"
        elif event.action == "read_electrical":
            message = (
                f"Battery {self._battery_voltage:.1f} volts {int(self._battery_percent)} percent"
            )
        elif event.action == "read_fuel":
            fuel_minutes = self._fuel_remaining_minutes or 0.0
            hours = int(fuel_minutes / 60)
            minutes = int(fuel_minutes % 60)
            if hours > 0:
                message = f"Fuel {self._fuel_quantity:.1f} gallons remaining {hours} hours {minutes} minutes"
            else:
                message = f"Fuel {self._fuel_quantity:.1f} gallons remaining {minutes} minutes"

        # Trim readouts
        elif event.action == "read_pitch_trim":
            # Convert trim value (-1.0 to 1.0) to percentage (0-100) for announcement
            trim_percent = int((self._pitch_trim + 1.0) * 50)
            message = f"Pitch trim {trim_percent} percent"
        elif event.action == "read_rudder_trim":
            # Convert trim value (-1.0 to 1.0) to percentage (0-100) for announcement
            trim_percent = int((self._rudder_trim + 1.0) * 50)
            message = f"Rudder trim {trim_percent} percent"

        else:
            # Map actions to TTS announcements
            # Skip gear_toggle announcement for fixed gear aircraft
            action_messages = {}
            if not self._fixed_gear:
                action_messages["gear_toggle"] = "Gear " + (
                    "down" if self._last_gear_state > 0.5 else "up"
                )

            action_messages.update(
                {
                    "flaps_down": "Flaps extending",
                    "flaps_up": "Flaps retracting",
                    "throttle_increase": "Throttle increased",
                    "throttle_decrease": "Throttle decreased",
                    "throttle_full": "Full throttle",
                    "throttle_idle": "Throttle idle",
                    "brakes_on": "Brakes on",
                    "parking_brake_set": "Parking brake set",
                    "parking_brake_release": "Parking brake released",
                    "pause": "Paused",
                    "tts_next": "Next",
                }
            )

            message = action_messages.get(event.action)

        if not message:
            logger.debug(f"No TTS message for action: {event.action}")
            return

        from airborne.audio.tts.base import TTSPriority

        # Convert message to message key
        message_key = self._get_message_key(message, event.action)

        # Determine priority: instrument readouts should interrupt previous readouts
        is_instrument_readout = event.action in (
            "read_airspeed",
            "read_altitude",
            "read_heading",
            "read_vspeed",
            "read_engine",
            "read_electrical",
            "read_fuel",
            "read_attitude",
            "read_pitch_trim",
            "read_rudder_trim",
        )
        priority = TTSPriority.HIGH if is_instrument_readout else TTSPriority.NORMAL
        # Interrupt previous speech for instrument readouts
        interrupt = is_instrument_readout

        # Handle both str and list[str] cases
        if isinstance(message_key, list):
            # Log the list of keys for debugging
            logger.info(f"Speaking: {' '.join(message_key)} ({message})")
            # Pass the list directly to TTS provider for composable playback
            self.tts_provider.speak(message_key, priority=priority, interrupt=interrupt)  # type: ignore[arg-type]
        else:
            logger.info(f"Speaking: {message_key} ({message})")
            self.tts_provider.speak(message_key, priority=priority, interrupt=interrupt)

    def _get_message_key(self, message: str, action: str) -> str | list[str]:
        """Convert human-readable message to message key.

        Args:
            message: Human-readable message.
            action: Input action that triggered the message.

        Returns:
            Message key or list of message keys for YAML lookup.
        """
        from airborne.audio.tts.speech_messages import SpeechMessages

        # Map instrument reading actions to helper methods
        # Use concise format (no prefixes) for airspeed, altitude, and vertical speed
        if action == "read_airspeed":
            # Concise: just number + "knots" (no "Airspeed" prefix)
            exact_knots = int(round(self._airspeed))
            exact_knots = max(0, min(300, exact_knots))
            return [
                f"cockpit/number_{exact_knots}_autogen",
                SpeechMessages.MSG_WORD_KNOTS,
            ]
        elif action == "read_altitude":
            # Concise: just number + "feet" (no "Altitude" prefix)
            feet = int(self._altitude)
            return SpeechMessages._digits_to_keys(feet) + [SpeechMessages.MSG_WORD_FEET]
        elif action == "read_heading":
            return SpeechMessages.heading(int(self._heading))
        elif action == "read_vspeed":
            # Concise: just "climbing/descending" + number (no "Vertical speed" prefix, no "feet per minute" suffix)
            fpm = int(self._vspeed)
            if abs(fpm) < 50:
                return [SpeechMessages.MSG_LEVEL_FLIGHT]
            direction_word = (
                SpeechMessages.MSG_WORD_CLIMBING if fpm > 0 else SpeechMessages.MSG_WORD_DESCENDING
            )
            return [direction_word] + SpeechMessages._digits_to_keys(abs(fpm))
        elif action == "read_attitude":
            # For attitude, we read pitch first, then bank
            # Always include instrument names
            bank_int = int(self._bank)
            pitch_int = int(self._pitch)

            result = [SpeechMessages.MSG_WORD_PITCH]
            if abs(pitch_int) < 3:
                result.append(SpeechMessages.MSG_LEVEL_ATTITUDE)
            else:
                result.append(SpeechMessages.pitch(pitch_int))

            result.append(SpeechMessages.MSG_WORD_BANK)
            if abs(bank_int) < 3:
                result.append(SpeechMessages.MSG_LEVEL_ATTITUDE)
            else:
                result.append(SpeechMessages.bank(bank_int))

            return result

        # Engine instrument readouts
        elif action == "read_rpm":
            return SpeechMessages.engine_rpm(int(self._engine_rpm), self._engine_running)
        elif action == "read_manifold_pressure":
            return SpeechMessages.manifold_pressure(self._manifold_pressure)
        elif action == "read_oil_pressure":
            return SpeechMessages.oil_pressure(int(self._oil_pressure))
        elif action == "read_oil_temp":
            # Convert Celsius to Fahrenheit
            oil_temp_f = self._oil_temp * 9 / 5 + 32
            return SpeechMessages.oil_temperature(int(oil_temp_f))
        elif action == "read_fuel_flow":
            return SpeechMessages.fuel_flow(self._fuel_flow)

        # Electrical instrument readouts
        elif action == "read_battery_voltage":
            return SpeechMessages.battery_voltage(self._battery_voltage)
        elif action == "read_battery_percent":
            return SpeechMessages.battery_percent(int(self._battery_percent))
        elif action == "read_battery_status":
            return SpeechMessages.battery_status(self._battery_current)
        elif action == "read_alternator":
            return SpeechMessages.alternator_output(self._alternator_output)

        # Fuel instrument readouts
        elif action == "read_fuel_quantity":
            return SpeechMessages.fuel_quantity(self._fuel_quantity)
        elif action == "read_fuel_remaining":
            return SpeechMessages.fuel_remaining(self._fuel_remaining_minutes or 0.0)

        # Comprehensive status readouts - return first message, queue rest
        elif action == "read_engine":
            # Comprehensive engine status (RPM)
            return SpeechMessages.engine_status(int(self._engine_rpm), self._engine_running)

        elif action == "read_electrical":
            # Comprehensive electrical status (voltage, percent, charging/discharging)
            return SpeechMessages.electrical_status(
                self._battery_voltage, int(self._battery_percent), self._battery_current
            )

        elif action == "read_fuel":
            # Comprehensive fuel status (quantity, remaining time)
            return SpeechMessages.fuel_status(
                self._fuel_quantity, self._fuel_remaining_minutes or 0.0
            )

        # Trim readouts
        elif action == "read_pitch_trim":
            # Convert trim value (-1.0 to 1.0) to percentage (0-100)
            trim_percent = int((self._pitch_trim + 1.0) * 50)
            return SpeechMessages.trim_position(trim_percent)
        elif action == "read_rudder_trim":
            # Convert trim value (-1.0 to 1.0) to percentage (0-100)
            trim_percent = int((self._rudder_trim + 1.0) * 50)
            return SpeechMessages.rudder_trim_position(trim_percent)

        # Map action messages to constants
        action_to_key = {
            "Gear down": SpeechMessages.MSG_GEAR_DOWN,
            "Gear up": SpeechMessages.MSG_GEAR_UP,
            "Flaps extending": SpeechMessages.MSG_FLAPS_EXTENDING,
            "Flaps retracting": SpeechMessages.MSG_FLAPS_RETRACTING,
            "Throttle increased": SpeechMessages.MSG_THROTTLE_INCREASED,
            "Throttle decreased": SpeechMessages.MSG_THROTTLE_DECREASED,
            "Full throttle": SpeechMessages.MSG_FULL_THROTTLE,
            "Throttle idle": SpeechMessages.MSG_THROTTLE_IDLE,
            "Brakes on": SpeechMessages.MSG_BRAKES_ON,
            "Parking brake set": SpeechMessages.MSG_PARKING_BRAKE_SET,
            "Parking brake released": SpeechMessages.MSG_PARKING_BRAKE_RELEASED,
            "Paused": SpeechMessages.MSG_PAUSED,
            "Next": SpeechMessages.MSG_NEXT,
            "Level flight": SpeechMessages.MSG_LEVEL_FLIGHT,
            "Level attitude": SpeechMessages.MSG_LEVEL_ATTITUDE,
        }

        return action_to_key.get(message, SpeechMessages.MSG_ERROR)

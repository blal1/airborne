"""FMOD audio engine implementation.

This module provides a concrete implementation of the IAudioEngine interface
using the pyfmodex library for high-quality 3D spatial audio.

Typical usage example:
    from airborne.audio.engine.fmod_engine import FMODEngine

    engine = FMODEngine()
    engine.initialize({"max_channels": 32})
    sound = engine.load_sound("sounds/engine.wav")
    source_id = engine.play_3d(sound, Vector3(0, 0, 10))
"""

from pathlib import Path
from typing import Any

try:
    import pyfmodex  # type: ignore[import-untyped]

    FMOD_AVAILABLE = True
except ImportError:
    FMOD_AVAILABLE = False
    pyfmodex = None

from airborne.audio.engine.base import (
    AudioFormat,
    IAudioEngine,
    Sound,
    SourceState,
    Vector3,
)
from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class FMODError(Exception):
    """Raised when FMOD operations fail."""


class FMODEngine(IAudioEngine):
    """FMOD-based audio engine with 3D spatial audio support.

    Provides high-quality audio playback with 3D positioning, doppler effect,
    and multiple simultaneous sources using the FMOD library.

    Examples:
        >>> engine = FMODEngine()
        >>> engine.initialize({"max_channels": 32})
        >>> sound = engine.load_sound("sounds/beep.wav")
        >>> source_id = engine.play_3d(sound, Vector3(10, 0, 0))
        >>> engine.shutdown()
    """

    def __init__(self) -> None:
        """Initialize the FMOD engine (not started yet)."""
        if not FMOD_AVAILABLE:
            raise ImportError("pyfmodex is not installed. Install it with: uv add pyfmodex")

        self._initialized = False
        self._system: Any = None  # pyfmodex.System
        self._sounds: dict[str, Sound] = {}
        self._channels: dict[int, Any] = {}  # channel objects
        self._next_source_id = 1
        self._master_volume = 1.0

    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize FMOD audio system.

        Args:
            config: Configuration with keys:
                - max_channels: Maximum number of channels (default: 32)

        Raises:
            FMODError: If initialization fails.
        """
        if self._initialized:
            logger.warning("FMOD engine already initialized")
            return

        try:
            self._system = pyfmodex.System()
            # Initialize FMOD with sufficient channels
            max_channels = config.get("max_channels", 32)
            self._system.init(maxchannels=max_channels)
            self._initialized = True
            logger.info(f"FMOD initialized successfully (max_channels={max_channels})")
        except Exception as e:
            raise FMODError(f"Failed to initialize FMOD: {e}") from e

    def shutdown(self) -> None:
        """Shutdown the FMOD engine.

        Stops all sources, unloads sounds, and releases resources.
        """
        if not self._initialized:
            return

        # Stop all channels
        for channel in self._channels.values():
            try:
                if channel and channel.is_playing:
                    channel.stop()
            except Exception as e:
                logger.warning(f"Error stopping channel: {e}")

        # Unload all sounds
        for sound in list(self._sounds.values()):
            try:
                self.unload_sound(sound)
            except Exception as e:
                logger.warning(f"Error unloading sound: {e}")

        # Release FMOD system
        if self._system:
            try:
                self._system.release()
            except Exception as e:
                logger.warning(f"Error releasing FMOD system: {e}")

        self._initialized = False
        self._channels.clear()
        logger.info("FMOD engine shut down")

    def load_sound_from_bytes(
        self,
        audio_bytes: bytes,
        name: str = "memory_sound",
    ) -> Sound:
        """Load a sound from raw audio file bytes in memory.

        FMOD will decode the audio format automatically (WAV, AIFF, MP3, etc.).
        This is the simplest way to play dynamically generated audio.

        Args:
            audio_bytes: Raw audio file bytes (WAV, AIFF, MP3, etc.).
            name: Identifier name for the sound.

        Returns:
            Loaded sound resource.

        Raises:
            FMODError: If loading fails.

        Examples:
            >>> audio_bytes, fmt = tts.generate_audio_bytes("Hello")
            >>> sound = engine.load_sound_from_bytes(audio_bytes)
            >>> engine.play_2d(sound)
        """
        if not self._initialized:
            raise FMODError("Engine not initialized")

        import ctypes

        from pyfmodex.structures import CREATESOUNDEXINFO

        try:
            # Set up CREATESOUNDEXINFO for memory loading
            exinfo = CREATESOUNDEXINFO()
            exinfo.cbsize = ctypes.sizeof(CREATESOUNDEXINFO)
            exinfo.length = len(audio_bytes)

            # Create sound from memory - FMOD will auto-detect format
            mode_flags = (
                pyfmodex.flags.MODE.OPENMEMORY
                | pyfmodex.flags.MODE.CREATESAMPLE
                | pyfmodex.flags.MODE.TWOD
            )

            fmod_sound = self._system.create_sound(audio_bytes, mode=mode_flags, exinfo=exinfo)

            # Create Sound object
            sound = Sound(
                path=name,
                format=AudioFormat.UNKNOWN,  # Let FMOD figure it out
                duration=0.0,
                sample_rate=44100,
                channels=2,
                handle=fmod_sound,
            )

            # Store in sounds dict with unique name
            unique_name = f"{name}_{id(sound)}"
            self._sounds[unique_name] = sound
            sound.path = unique_name

            logger.debug(
                "Loaded sound from bytes: %s (%d bytes)",
                unique_name,
                len(audio_bytes),
            )
            return sound

        except Exception as e:
            raise FMODError(f"Failed to load sound from bytes: {e}") from e

    def load_sound_from_memory(
        self,
        pcm_data: bytes,
        sample_rate: int,
        channels: int,
        name: str = "memory_sound",
    ) -> Sound:
        """Load a sound from raw PCM data in memory.

        This allows playing dynamically generated audio (like TTS) without
        writing to disk.

        Args:
            pcm_data: Raw PCM samples as bytes (16-bit signed, little-endian).
            sample_rate: Sample rate in Hz (e.g., 22050, 44100).
            channels: Number of channels (1=mono, 2=stereo).
            name: Identifier name for the sound.

        Returns:
            Loaded sound resource.

        Raises:
            FMODError: If loading fails.

        Examples:
            >>> pcm_bytes = tts.generate_pcm("Hello").bytes
            >>> sound = engine.load_sound_from_memory(pcm_bytes, 22050, 1)
            >>> engine.play_2d(sound)
        """
        if not self._initialized:
            raise FMODError("Engine not initialized")

        import ctypes

        from pyfmodex.structures import CREATESOUNDEXINFO

        try:
            # Create WAV header + PCM data in memory
            # FMOD can decode WAV format from memory with OPENMEMORY
            wav_data = self._create_wav_buffer(pcm_data, sample_rate, channels)

            # Set up CREATESOUNDEXINFO for memory loading
            exinfo = CREATESOUNDEXINFO()
            exinfo.cbsize = ctypes.sizeof(CREATESOUNDEXINFO)
            exinfo.length = len(wav_data)

            # Create sound from memory
            # OPENMEMORY tells FMOD the "path" is actually a memory pointer
            mode_flags = (
                pyfmodex.flags.MODE.OPENMEMORY
                | pyfmodex.flags.MODE.CREATESAMPLE
                | pyfmodex.flags.MODE.TWOD
            )

            fmod_sound = self._system.create_sound(wav_data, mode=mode_flags, exinfo=exinfo)

            # Create Sound object
            sound = Sound(
                path=name,
                format=AudioFormat.WAV,
                duration=len(pcm_data) / (sample_rate * channels * 2),  # 2 bytes per sample
                sample_rate=sample_rate,
                channels=channels,
                handle=fmod_sound,
            )

            # Store in sounds dict with unique name
            unique_name = f"{name}_{id(sound)}"
            self._sounds[unique_name] = sound
            sound.path = unique_name

            logger.debug(
                "Loaded sound from memory: %s (%d bytes, %dHz, %dch)",
                unique_name,
                len(pcm_data),
                sample_rate,
                channels,
            )
            return sound

        except Exception as e:
            raise FMODError(f"Failed to load sound from memory: {e}") from e

    def _create_wav_buffer(self, pcm_data: bytes, sample_rate: int, channels: int) -> bytes:
        """Create a WAV file buffer in memory from raw PCM data.

        Args:
            pcm_data: Raw PCM samples (16-bit signed, little-endian).
            sample_rate: Sample rate in Hz.
            channels: Number of channels.

        Returns:
            Complete WAV file as bytes.
        """
        import struct

        # WAV header parameters
        bits_per_sample = 16
        byte_rate = sample_rate * channels * bits_per_sample // 8
        block_align = channels * bits_per_sample // 8
        data_size = len(pcm_data)
        file_size = 36 + data_size  # Header size (44) - 8 + data

        # Build WAV header
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",  # ChunkID
            file_size,  # ChunkSize
            b"WAVE",  # Format
            b"fmt ",  # Subchunk1ID
            16,  # Subchunk1Size (PCM = 16)
            1,  # AudioFormat (PCM = 1)
            channels,  # NumChannels
            sample_rate,  # SampleRate
            byte_rate,  # ByteRate
            block_align,  # BlockAlign
            bits_per_sample,  # BitsPerSample
            b"data",  # Subchunk2ID
            data_size,  # Subchunk2Size
        )

        return header + pcm_data

    def load_sound(self, path: str, preload: bool = True, loop_mode: bool = False) -> Sound:
        """Load a sound from file.

        Args:
            path: Path to the sound file.
            preload: Whether to load into memory (True) or stream (False).
            loop_mode: Whether to enable loop mode on the sound itself (True) or not (False).

        Returns:
            Loaded sound resource.

        Raises:
            FileNotFoundError: If sound file not found.
            FMODError: If loading fails.
        """
        if not self._initialized:
            raise FMODError("Engine not initialized")

        # Check if already loaded
        if path in self._sounds:
            return self._sounds[path]

        # Check file exists
        if not Path(path).exists():
            raise FileNotFoundError(f"Sound file not found: {path}")

        try:
            # Create sound with explicit mode flags
            # FMOD_DEFAULT includes format detection and appropriate codec selection
            mode_flags = pyfmodex.flags.MODE.DEFAULT

            # Add loop mode if requested
            if loop_mode:
                mode_flags |= pyfmodex.flags.MODE.LOOP_NORMAL

            if preload:
                # Load entire sound into memory
                fmod_sound = self._system.create_sound(
                    path, mode=mode_flags | pyfmodex.flags.MODE.CREATESAMPLE
                )
            else:
                # Stream from disk
                fmod_sound = self._system.create_stream(
                    path, mode=mode_flags | pyfmodex.flags.MODE.CREATESTREAM
                )

            # Detect format from extension
            ext = Path(path).suffix.lower()
            format_map = {
                ".wav": AudioFormat.WAV,
                ".mp3": AudioFormat.MP3,
                ".ogg": AudioFormat.OGG,
                ".flac": AudioFormat.FLAC,
            }
            audio_format = format_map.get(ext, AudioFormat.UNKNOWN)

            # Create Sound object (duration not critical for playback)
            sound = Sound(
                path=path,
                format=audio_format,
                duration=0.0,  # Duration not needed for looping sounds
                sample_rate=44100,  # FMOD default
                channels=2,  # Assume stereo
                handle=fmod_sound,
            )

            self._sounds[path] = sound
            logger.info(f"Loaded sound: {path}")
            return sound

        except Exception as e:
            raise FMODError(f"Failed to load sound {path}: {e}") from e

    def unload_sound(self, sound: Sound) -> None:
        """Unload a sound and free resources.

        Args:
            sound: Sound to unload.
        """
        try:
            if sound.handle:
                sound.handle.release()
            if sound.path in self._sounds:
                del self._sounds[sound.path]
            logger.debug(f"Unloaded sound: {sound.path}")
        except Exception as e:
            logger.warning(f"Error unloading sound {sound.path}: {e}")

    def play_2d(
        self, sound: Sound, volume: float = 1.0, pitch: float = 1.0, loop: bool = False
    ) -> int:
        """Play a sound in 2D (no spatial positioning).

        Args:
            sound: Sound to play.
            volume: Volume level (0.0 to 1.0).
            pitch: Pitch multiplier (1.0 = normal).
            loop: Whether to loop the sound.

        Returns:
            Source ID for controlling playback.
        """
        if not self._initialized:
            raise FMODError("Engine not initialized")

        try:
            # Play sound (paused initially to set properties)
            channel = sound.handle.play(paused=True)
            source_id = self._next_source_id
            self._next_source_id += 1

            # Set properties
            channel.volume = volume * self._master_volume
            channel.pitch = pitch
            if loop:
                channel.loop_count = -1  # Infinite loop
            else:
                channel.loop_count = 0

            # Set 2D mode (no 3D positioning)
            channel.mode = pyfmodex.flags.MODE.TWOD

            # Start playback
            channel.paused = False

            # Store channel
            self._channels[source_id] = channel

            logger.debug(f"Playing 2D sound: {sound.path} (source_id={source_id})")
            return source_id

        except Exception as e:
            raise FMODError(f"Failed to play sound {sound.path}: {e}") from e

    def play_3d(
        self,
        sound: Sound,
        position: Vector3,
        velocity: Vector3 | None = None,
        volume: float = 1.0,
        pitch: float = 1.0,
        loop: bool = False,
    ) -> int:
        """Play a sound in 3D space.

        Args:
            sound: Sound to play.
            position: 3D position in world space.
            velocity: 3D velocity for doppler effect.
            volume: Volume level (0.0 to 1.0).
            pitch: Pitch multiplier (1.0 = normal).
            loop: Whether to loop the sound.

        Returns:
            Source ID for controlling playback.
        """
        if not self._initialized:
            raise FMODError("Engine not initialized")

        try:
            # Play sound (paused initially to set properties)
            channel = sound.handle.play(paused=True)
            source_id = self._next_source_id
            self._next_source_id += 1

            # Set properties
            channel.volume = volume * self._master_volume
            channel.pitch = pitch
            if loop:
                channel.loop_count = -1  # Infinite loop
            else:
                channel.loop_count = 0

            # Set 3D mode
            channel.mode = pyfmodex.flags.MODE.THREED

            # Set 3D position
            channel.position = [position.x, position.y, position.z]

            # Set velocity if provided
            if velocity:
                channel.velocity = [velocity.x, velocity.y, velocity.z]
            else:
                channel.velocity = [0.0, 0.0, 0.0]

            # Start playback
            channel.paused = False

            # Store channel
            self._channels[source_id] = channel

            logger.debug(
                f"Playing 3D sound: {sound.path} at ({position.x}, {position.y}, {position.z}) "
                f"(source_id={source_id})"
            )
            return source_id

        except Exception as e:
            raise FMODError(f"Failed to play 3D sound {sound.path}: {e}") from e

    def stop_source(self, source_id: int) -> None:
        """Stop a playing source.

        Args:
            source_id: ID of source to stop.
        """
        channel = self._channels.get(source_id)
        if channel:
            try:
                channel.stop()
                del self._channels[source_id]
                logger.debug(f"Stopped source: {source_id}")
            except Exception as e:
                logger.warning(f"Error stopping source {source_id}: {e}")

    def pause_source(self, source_id: int) -> None:
        """Pause a playing source.

        Args:
            source_id: ID of source to pause.
        """
        channel = self._channels.get(source_id)
        if channel:
            try:
                channel.paused = True
                logger.debug(f"Paused source: {source_id}")
            except Exception as e:
                logger.warning(f"Error pausing source {source_id}: {e}")

    def resume_source(self, source_id: int) -> None:
        """Resume a paused source.

        Args:
            source_id: ID of source to resume.
        """
        channel = self._channels.get(source_id)
        if channel:
            try:
                channel.paused = False
                logger.debug(f"Resumed source: {source_id}")
            except Exception as e:
                logger.warning(f"Error resuming source {source_id}: {e}")

    def update_source_position(
        self, source_id: int, position: Vector3, velocity: Vector3 | None = None
    ) -> None:
        """Update a source's position and velocity.

        Args:
            source_id: ID of source to update.
            position: New 3D position.
            velocity: New 3D velocity (for doppler).
        """
        channel = self._channels.get(source_id)
        if channel:
            try:
                channel.position = [position.x, position.y, position.z]
                if velocity:
                    channel.velocity = [velocity.x, velocity.y, velocity.z]
            except Exception as e:
                logger.warning(f"Error updating source {source_id} position: {e}")

    def update_source_volume(self, source_id: int, volume: float) -> None:
        """Update a source's volume.

        Args:
            source_id: ID of source to update.
            volume: New volume level (0.0 to 1.0).
        """
        channel = self._channels.get(source_id)
        if channel:
            try:
                # Check if channel is still valid
                if channel.is_playing:
                    channel.volume = volume * self._master_volume
            except Exception:
                # Remove invalid channel
                if source_id in self._channels:
                    del self._channels[source_id]

    def update_source_pitch(self, source_id: int, pitch: float) -> None:
        """Update a source's pitch.

        Args:
            source_id: ID of source to update.
            pitch: New pitch multiplier (1.0 = normal).
        """
        channel = self._channels.get(source_id)
        if channel:
            try:
                # Check if channel is still valid
                if channel.is_playing:
                    channel.pitch = pitch
            except Exception:
                # Remove invalid channel
                if source_id in self._channels:
                    del self._channels[source_id]

    def set_listener(
        self,
        position: Vector3,
        forward: Vector3,
        up: Vector3,
        velocity: Vector3 | None = None,
    ) -> None:
        """Set listener (player) position and orientation.

        Args:
            position: Listener 3D position.
            forward: Forward direction vector (normalized).
            up: Up direction vector (normalized).
            velocity: Listener velocity for doppler.
        """
        if not self._initialized or not self._system:
            return

        try:
            import math

            # Validate all floats are valid (not NaN or infinite)
            def is_valid_float(val: float) -> bool:
                return not (math.isnan(val) or math.isinf(val))

            # Check position
            if not all(is_valid_float(v) for v in [position.x, position.y, position.z]):
                logger.warning(f"Invalid position values: {position}")
                return

            # Check forward
            if not all(is_valid_float(v) for v in [forward.x, forward.y, forward.z]):
                logger.warning(f"Invalid forward values: {forward}")
                return

            # Check up
            if not all(is_valid_float(v) for v in [up.x, up.y, up.z]):
                logger.warning(f"Invalid up values: {up}")
                return

            listener = self._system.listener()
            listener.position = [position.x, position.y, position.z]
            listener.forward = [forward.x, forward.y, forward.z]
            listener.up = [up.x, up.y, up.z]

            if velocity:
                if all(is_valid_float(v) for v in [velocity.x, velocity.y, velocity.z]):
                    listener.velocity = [velocity.x, velocity.y, velocity.z]
                else:
                    listener.velocity = [0.0, 0.0, 0.0]
            else:
                listener.velocity = [0.0, 0.0, 0.0]

        except Exception as e:
            logger.warning(f"Error setting listener: {e}")

    def get_source_state(self, source_id: int) -> SourceState:
        """Get the current state of a source.

        Args:
            source_id: ID of source to query.

        Returns:
            Current source state.
        """
        channel = self._channels.get(source_id)
        if not channel:
            return SourceState.STOPPED

        try:
            if not channel.is_playing:
                return SourceState.STOPPED
            if channel.paused:
                return SourceState.PAUSED
            return SourceState.PLAYING
        except Exception:
            return SourceState.STOPPED

    def set_master_volume(self, volume: float) -> None:
        """Set the master volume for all sounds.

        Args:
            volume: Master volume level (0.0 to 1.0).
        """
        self._master_volume = max(0.0, min(1.0, volume))

        # Update all active channels
        for channel in self._channels.values():
            try:
                if channel:
                    # Reapply volume with new master volume
                    current_vol = (
                        channel.volume / self._master_volume if self._master_volume > 0 else 1.0
                    )
                    channel.volume = current_vol * self._master_volume
            except Exception as e:
                logger.warning(f"Error updating channel volume: {e}")

        logger.debug(f"Set master volume to {self._master_volume:.2f}")

    def update(self) -> None:
        """Update FMOD system.

        Should be called once per frame to process audio.
        """
        if self._initialized and self._system:
            try:
                self._system.update()
            except Exception as e:
                logger.warning(f"Error updating FMOD system: {e}")

            # Clean up stopped channels (check each channel individually)
            stopped_ids = []
            for source_id, channel in list(self._channels.items()):
                try:
                    if not channel or not channel.is_playing:
                        stopped_ids.append(source_id)
                except Exception:
                    # Channel is invalid, mark for removal
                    stopped_ids.append(source_id)

            for source_id in stopped_ids:
                del self._channels[source_id]

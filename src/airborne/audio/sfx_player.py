"""Sound effects player with category-based volume control.

This module provides sound effect playback functionality with support for
multiple volume categories and proper volume scaling.

Typical usage example:
    from airborne.audio.sfx_player import SFXPlayer

    sfx = SFXPlayer(audio_engine, volume_manager)
    source_id = sfx.play("click.wav", category="ui")
    sfx.stop(source_id)
"""

from typing import Any

from airborne.audio.volume_manager import VolumeCategory


class SFXPlayer:
    """Manages sound effect playback with category volumes.

    The SFXPlayer handles one-shot sound effects with volume control
    integrated with the VolumeManager's category system.

    Examples:
        >>> sfx = SFXPlayer(audio_engine, volume_manager)
        >>> sfx.play("click.wav", category="ui", volume=0.8)
        42
    """

    def __init__(self, audio_engine: Any, volume_manager: Any) -> None:
        """Initialize the SFX player.

        Args:
            audio_engine: Audio engine with play_2d/play_3d/stop_source.
            volume_manager: VolumeManager for category volumes.
        """
        self._audio_engine = audio_engine
        self._volume_manager = volume_manager

    def play(
        self,
        file_path: str,
        category: VolumeCategory = "ui",
        volume: float = 1.0,
        loop: bool = False,
    ) -> int | None:
        """Play a sound effect.

        Args:
            file_path: Path to sound file to play.
            category: Volume category (ui, cockpit, engine, etc.).
            volume: Volume multiplier (0.0 to 1.0), scaled by category volume.
            loop: Whether to loop the sound.

        Returns:
            Source ID for the playing sound, or None if playback failed.

        Examples:
            >>> sfx.play("click.wav", category="ui", volume=0.8)
            42
        """
        # Calculate final volume (category volume * volume parameter)
        final_volume = self._volume_manager.get_final_volume(category) * volume

        # Load the sound file
        sound = self._audio_engine.load_sound(file_path, preload=True, loop_mode=loop)

        # Play the sound as 2D audio
        source_id = self._audio_engine.play_2d(sound, loop=loop, volume=final_volume)

        return source_id

    def play_3d(
        self,
        file_path: str,
        position: tuple[float, float, float],
        category: VolumeCategory = "environment",
        volume: float = 1.0,
        loop: bool = False,
    ) -> int | None:
        """Play a 3D positional sound effect.

        Args:
            file_path: Path to sound file to play.
            position: 3D position (x, y, z) for the sound.
            category: Volume category (environment, engine, etc.).
            volume: Volume multiplier (0.0 to 1.0), scaled by category volume.
            loop: Whether to loop the sound.

        Returns:
            Source ID for the playing sound, or None if playback failed.

        Examples:
            >>> sfx.play_3d("engine.wav", (0, 0, 10), category="engine")
            43
        """
        # Calculate final volume (category volume * volume parameter)
        final_volume = self._volume_manager.get_final_volume(category) * volume

        # Load the sound file
        sound = self._audio_engine.load_sound(file_path, preload=True, loop_mode=loop)

        # Play the sound as 3D audio
        source_id = self._audio_engine.play_3d(
            sound, position=position, loop=loop, volume=final_volume
        )

        return source_id

    def stop(self, source_id: int) -> None:
        """Stop a playing sound effect.

        Args:
            source_id: Source ID from play() or play_3d().

        Examples:
            >>> sfx.stop(42)
        """
        self._audio_engine.stop_source(source_id)

    def set_volume(self, source_id: int, category: VolumeCategory, volume: float) -> None:
        """Set volume for a playing sound effect.

        Args:
            source_id: Source ID from play() or play_3d().
            category: Volume category for proper scaling.
            volume: Volume multiplier (0.0 to 1.0), scaled by category volume.

        Examples:
            >>> sfx.set_volume(42, "ui", 0.5)
        """
        final_volume = self._volume_manager.get_final_volume(category) * volume
        self._audio_engine.set_source_volume(source_id, final_volume)

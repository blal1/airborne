"""Unified audio API facade combining all audio subsystems.

This module provides a single facade interface for all audio functionality,
combining music playback, sound effects, volume management, and audio effects.

Typical usage example:
    from airborne.audio.audio_facade import AudioFacade

    audio = AudioFacade(fmod_engine)
    audio.music.play("menu.ogg", loop=True, fade_in=1.0)
    audio.sfx.play("click.wav", category="ui")
    audio.volumes.set_master_volume(0.8)
"""

from typing import Any

from airborne.audio.effects.base import EffectManager
from airborne.audio.music_player import MusicPlayer
from airborne.audio.sfx_player import SFXPlayer
from airborne.audio.volume_manager import VolumeManager


class AudioFacade:
    """Unified interface for all audio functionality.

    The AudioFacade combines music playback, sound effects, volume
    management, and audio effects into a single unified API.

    Examples:
        >>> audio = AudioFacade(fmod_engine)
        >>> audio.music.play("menu.ogg", loop=True)
        >>> audio.sfx.play("click.wav", category="ui")
        >>> audio.volumes.set_master_volume(0.8)
    """

    def __init__(self, audio_engine: Any) -> None:
        """Initialize the audio facade.

        Args:
            audio_engine: Audio engine (e.g., FMODEngine).

        Examples:
            >>> audio = AudioFacade(fmod_engine)
        """
        self._audio_engine = audio_engine

        # Initialize subsystems
        self.volumes = VolumeManager()
        self.effects = EffectManager(audio_engine)
        self.music = MusicPlayer(audio_engine, self.volumes)
        self.sfx = SFXPlayer(audio_engine, self.volumes)

    def update(self, delta_time: float) -> None:
        """Update audio subsystems (call each frame).

        This handles time-based updates like music fading.

        Args:
            delta_time: Time since last update in seconds.

        Examples:
            >>> audio.update(0.016)  # ~60 FPS
        """
        self.music.update(delta_time)

    def shutdown(self) -> None:
        """Shutdown audio subsystems.

        Stops all playback and cleans up resources.

        Examples:
            >>> audio.shutdown()
        """
        self.music.stop()
        self.effects.clear_all_effects()

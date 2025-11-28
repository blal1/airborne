"""Audio effect protocol and effect manager.

This module defines the IAudioEffect protocol that all audio effects must
implement, and the EffectManager class for managing named effects.

Typical usage example:
    from airborne.audio.effects.base import EffectManager
    from airborne.audio.effects.radio_filter import RadioEffectFilter

    manager = EffectManager(fmod_engine)
    manager.register_effect("radio", radio_effect)
    manager.apply_effect("radio", source_id)
    manager.remove_effect(source_id)
"""

from typing import Any, Protocol


class IAudioEffect(Protocol):
    """Protocol for audio effects that can be applied to channels.

    All audio effects must implement this protocol to work with the
    EffectManager. This allows for dynamic effect application and removal.

    Examples:
        >>> class CustomEffect:
        ...     def apply_to_channel(self, channel: Any) -> None:
        ...         # Apply DSP chain to channel
        ...         pass
        ...
        ...     def remove_from_channel(self, channel: Any) -> None:
        ...         # Remove DSP chain from channel
        ...         pass
    """

    def apply_to_channel(self, channel: Any) -> None:
        """Apply this effect to an FMOD channel.

        Args:
            channel: FMOD Channel to apply effect to.
        """
        ...

    def remove_from_channel(self, channel: Any) -> None:
        """Remove this effect from an FMOD channel.

        Args:
            channel: FMOD Channel to remove effect from.
        """
        ...


class EffectManager:
    """Manages named audio effects and their application to channels.

    The EffectManager allows registering effects by name and applying them
    to audio channels via their source IDs. It tracks which effects are
    applied to which channels for proper cleanup.

    Examples:
        >>> manager = EffectManager(fmod_engine)
        >>> manager.register_effect("radio", radio_effect)
        >>> manager.apply_effect("radio", source_id)
        >>> manager.remove_effect(source_id)
    """

    def __init__(self, audio_engine: Any) -> None:
        """Initialize the effect manager.

        Args:
            audio_engine: Audio engine with get_channel() method.
        """
        self._audio_engine = audio_engine
        self._effects: dict[str, IAudioEffect] = {}
        self._applied_effects: dict[int, str] = {}  # source_id -> effect_name

    def register_effect(self, name: str, effect: IAudioEffect) -> None:
        """Register a named effect.

        Args:
            name: Unique name for the effect (e.g., "radio", "reverb").
            effect: Effect instance implementing IAudioEffect protocol.

        Examples:
            >>> manager.register_effect("radio", RadioEffectFilter(...))
        """
        self._effects[name] = effect

    def unregister_effect(self, name: str) -> None:
        """Unregister a named effect.

        Args:
            name: Name of effect to remove.

        Note:
            This does not remove the effect from channels it's applied to.
            Call remove_effect() first if needed.
        """
        self._effects.pop(name, None)

    def apply_effect(self, effect_name: str, source_id: int) -> bool:
        """Apply a named effect to a channel.

        Args:
            effect_name: Name of registered effect to apply.
            source_id: Source ID of channel to apply effect to.

        Returns:
            True if effect was applied, False if effect not found or
            channel not found.

        Examples:
            >>> success = manager.apply_effect("radio", 42)
        """
        effect = self._effects.get(effect_name)
        if not effect:
            return False

        channel = self._audio_engine.get_channel(source_id)
        if not channel:
            return False

        # Remove any existing effect from this channel
        if source_id in self._applied_effects:
            self.remove_effect(source_id)

        # Apply new effect
        effect.apply_to_channel(channel)
        self._applied_effects[source_id] = effect_name
        return True

    def remove_effect(self, source_id: int) -> bool:
        """Remove effect from a channel.

        Args:
            source_id: Source ID of channel to remove effect from.

        Returns:
            True if effect was removed, False if no effect applied or
            channel not found.

        Examples:
            >>> success = manager.remove_effect(42)
        """
        effect_name = self._applied_effects.get(source_id)
        if not effect_name:
            return False

        effect = self._effects.get(effect_name)
        if not effect:
            # Effect was unregistered but still tracked - clean up tracking
            del self._applied_effects[source_id]
            return False

        channel = self._audio_engine.get_channel(source_id)
        if channel:
            effect.remove_from_channel(channel)

        del self._applied_effects[source_id]
        return True

    def get_applied_effect(self, source_id: int) -> str | None:
        """Get the name of the effect applied to a channel.

        Args:
            source_id: Source ID to query.

        Returns:
            Name of applied effect, or None if no effect applied.

        Examples:
            >>> effect_name = manager.get_applied_effect(42)
            >>> print(effect_name)  # "radio"
        """
        return self._applied_effects.get(source_id)

    def clear_all_effects(self) -> None:
        """Remove all effects from all channels and clear tracking.

        This is useful for cleanup during shutdown.
        """
        # Remove effects from all channels
        for source_id in list(self._applied_effects.keys()):
            self.remove_effect(source_id)

        self._applied_effects.clear()

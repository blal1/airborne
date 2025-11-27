"""Radio system abstraction for different aircraft radio interfaces.

Different aircraft have different radio systems (dual-knob, G1000, touchscreen, etc.).
This module provides the base interface and implementations for various radio systems.

Typical usage:
    # In aircraft config:
    radio_system: "dual_knob"  # or "g1000", "cursor_keypad"

    # RadioPlugin loads the appropriate system:
    system = RadioSystemFactory.create(config["radio_system"], ...)
    system.handle_input(action)
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from airborne.plugins.radio.frequency_announcer import FrequencyAnnouncer
from airborne.plugins.radio.frequency_manager import FrequencyManager, RadioType

if TYPE_CHECKING:
    from airborne.audio.sound_manager import SoundManager


class RadioSystem(ABC):
    """Base class for radio tuning systems.

    Different aircraft have different radio interfaces:
    - Dual-knob: Traditional KX-155 style (outer=MHz, inner=kHz)
    - G1000: Garmin glass cockpit with cursor/knobs
    - Cursor/Keypad: Business jets with number entry
    - Touchscreen: Modern glass with direct frequency entry

    Each system handles input differently and provides appropriate audio feedback.
    """

    def __init__(
        self,
        frequency_manager: FrequencyManager,
        frequency_announcer: FrequencyAnnouncer | None = None,
        sound_manager: "SoundManager | None" = None,
    ):
        """Initialize radio system.

        Args:
            frequency_manager: Frequency manager for tuning operations.
            frequency_announcer: Announcer for audio feedback (optional).
            sound_manager: Sound manager for playing click sounds (optional).
        """
        self.frequency_manager = frequency_manager
        self.frequency_announcer = frequency_announcer
        self.sound_manager = sound_manager
        self.selected_radio: RadioType = "COM1"

    @abstractmethod
    def handle_input(self, action: str, data: dict[str, Any] | None = None) -> bool:
        """Handle input action for this radio system.

        Args:
            action: Input action name (e.g., "outer_knob_increase").
            data: Optional data for the action.

        Returns:
            True if action was handled, False otherwise.
        """
        pass

    @abstractmethod
    def get_input_actions(self) -> list[str]:
        """Get list of input actions this system supports.

        Returns:
            List of action names (e.g., ["outer_knob_increase", "inner_knob_decrease"]).
        """
        pass

    def select_radio(self, radio: RadioType) -> None:
        """Select active radio for tuning.

        Args:
            radio: Radio to select ("COM1" or "COM2").
        """
        self.selected_radio = radio


class RadioSystemFactory:
    """Factory for creating radio systems."""

    _systems: dict[str, type[RadioSystem]] = {}

    @classmethod
    def register(cls, name: str, system_class: type[RadioSystem]) -> None:
        """Register a radio system type.

        Args:
            name: System name (e.g., "dual_knob").
            system_class: RadioSystem class to register.
        """
        cls._systems[name] = system_class

    @classmethod
    def create(
        cls,
        name: str,
        frequency_manager: FrequencyManager,
        frequency_announcer: FrequencyAnnouncer | None = None,
        sound_manager: "SoundManager | None" = None,
    ) -> RadioSystem:
        """Create a radio system by name.

        Args:
            name: System name (e.g., "dual_knob").
            frequency_manager: Frequency manager instance.
            frequency_announcer: Announcer instance (optional).
            sound_manager: Sound manager instance (optional).

        Returns:
            RadioSystem instance.

        Raises:
            ValueError: If system name not registered.
        """
        if name not in cls._systems:
            raise ValueError(
                f"Unknown radio system: {name}. Available: {list(cls._systems.keys())}"
            )
        return cls._systems[name](frequency_manager, frequency_announcer, sound_manager)

    @classmethod
    def list_systems(cls) -> list[str]:
        """Get list of registered radio systems.

        Returns:
            List of system names.
        """
        return list(cls._systems.keys())

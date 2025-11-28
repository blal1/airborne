"""Base widget class for audio-accessible UI components.

This module provides the base infrastructure for creating widgets that work
with audio-only interfaces. All widgets support:
- TTS announcements via cache service
- Click sounds for navigation feedback
- Keyboard input handling
- State management

Typical usage:
    class MyWidget(Widget):
        def handle_key(self, key: int, unicode: str) -> bool:
            # Handle key press
            return True  # Consumed the key
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class WidgetState(Enum):
    """Widget state enumeration."""

    INACTIVE = auto()  # Widget is not focused
    ACTIVE = auto()  # Widget is focused and accepting input
    EDITING = auto()  # Widget is in edit mode (for text inputs)


@dataclass
class WidgetEvent:
    """Event emitted by a widget.

    Attributes:
        widget_id: ID of the widget that emitted the event.
        event_type: Type of event (e.g., "value_changed", "submitted").
        value: Current value of the widget.
        data: Additional event-specific data.
    """

    widget_id: str
    event_type: str
    value: Any
    data: dict[str, Any] = field(default_factory=dict)


class Widget(ABC):
    """Base class for audio-accessible UI widgets.

    Provides common functionality for TTS announcements, click sounds,
    and state management. Subclasses implement specific widget behavior.

    Attributes:
        widget_id: Unique identifier for this widget.
        label: Human-readable label for TTS announcements.
        state: Current widget state (INACTIVE, ACTIVE, EDITING).
    """

    # Sound paths for UI feedback
    CLICK_KNOB = "assets/sounds/aircraft/click_knob.mp3"
    CLICK_SWITCH = "assets/sounds/aircraft/click_switch.mp3"
    CLICK_BUTTON = "assets/sounds/aircraft/click_button.mp3"

    def __init__(
        self,
        widget_id: str,
        label: str,
        on_change: Callable[[WidgetEvent], None] | None = None,
        on_submit: Callable[[WidgetEvent], None] | None = None,
    ) -> None:
        """Initialize widget.

        Args:
            widget_id: Unique identifier for this widget.
            label: Human-readable label for TTS announcements.
            on_change: Callback when value changes.
            on_submit: Callback when value is submitted (Enter pressed).
        """
        self.widget_id = widget_id
        self.label = label
        self.state = WidgetState.INACTIVE
        self._on_change = on_change
        self._on_submit = on_submit

        # TTS and audio callbacks (set by parent menu)
        self._speak_callback: Callable[[str], None] | None = None
        self._click_callback: Callable[[str], None] | None = None

    def set_audio_callbacks(
        self,
        speak: Callable[[str], None] | None = None,
        click: Callable[[str], None] | None = None,
    ) -> None:
        """Set audio callback functions.

        Args:
            speak: Function to speak text via TTS.
            click: Function to play click sound (pass sound file path).
        """
        self._speak_callback = speak
        self._click_callback = click

    def activate(self) -> None:
        """Activate the widget (give focus)."""
        self.state = WidgetState.ACTIVE
        self._announce_activation()

    def deactivate(self) -> None:
        """Deactivate the widget (remove focus)."""
        self.state = WidgetState.INACTIVE

    @abstractmethod
    def handle_key(self, key: int, unicode: str) -> bool:
        """Handle a key press.

        Args:
            key: pygame key code.
            unicode: Unicode character for the key.

        Returns:
            True if the key was consumed, False otherwise.
        """
        pass

    @abstractmethod
    def get_value(self) -> Any:
        """Get the current value of the widget.

        Returns:
            Current value (type depends on widget).
        """
        pass

    @abstractmethod
    def set_value(self, value: Any) -> None:
        """Set the value of the widget.

        Args:
            value: New value to set.
        """
        pass

    @abstractmethod
    def get_display_text(self) -> str:
        """Get text representation of current value for display/TTS.

        Returns:
            Human-readable text.
        """
        pass

    def _announce_activation(self) -> None:
        """Announce widget activation via TTS."""
        display = self.get_display_text()
        if display:
            self._speak(f"{self.label}: {display}")
        else:
            self._speak(self.label)

    def _speak(self, text: str) -> None:
        """Speak text via TTS.

        Args:
            text: Text to speak.
        """
        if self._speak_callback:
            self._speak_callback(text)
        else:
            logger.debug("TTS not available: %s", text)

    def _play_click(self, sound_type: str = "knob") -> None:
        """Play a click sound.

        Args:
            sound_type: Type of click ("knob", "switch", "button").
        """
        if not self._click_callback:
            return

        sound_map = {
            "knob": self.CLICK_KNOB,
            "switch": self.CLICK_SWITCH,
            "button": self.CLICK_BUTTON,
        }
        sound_path = sound_map.get(sound_type, self.CLICK_KNOB)
        self._click_callback(sound_path)

    def _emit_change(self) -> None:
        """Emit a value changed event."""
        if self._on_change:
            event = WidgetEvent(
                widget_id=self.widget_id,
                event_type="value_changed",
                value=self.get_value(),
            )
            self._on_change(event)

    def _emit_submit(self) -> None:
        """Emit a value submitted event."""
        if self._on_submit:
            event = WidgetEvent(
                widget_id=self.widget_id,
                event_type="submitted",
                value=self.get_value(),
            )
            self._on_submit(event)

"""Text input widget for audio-accessible interfaces.

This widget provides text input with:
- Direct keyboard typing
- Character-by-character TTS feedback
- Backspace/delete support
- Enter to submit

Typical usage:
    widget = TextInputWidget(
        widget_id="airport_icao",
        label="Departure Airport",
        on_submit=lambda e: print(f"Selected: {e.value}"),
    )
"""

import logging
from collections.abc import Callable
from typing import Any

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

from airborne.ui.widgets.base import Widget, WidgetState

logger = logging.getLogger(__name__)


class TextInputWidget(Widget):
    """Text input widget with audio feedback.

    Supports direct keyboard input with per-character TTS feedback.
    Press Enter to submit, Escape to cancel.

    Attributes:
        value: Current text value.
        max_length: Maximum allowed input length.
        uppercase: Whether to force uppercase input.
    """

    def __init__(
        self,
        widget_id: str,
        label: str,
        initial_value: str = "",
        max_length: int = 50,
        uppercase: bool = False,
        placeholder: str = "",
        on_change: Callable[[Any], None] | None = None,
        on_submit: Callable[[Any], None] | None = None,
    ) -> None:
        """Initialize text input widget.

        Args:
            widget_id: Unique identifier.
            label: Label for TTS announcements.
            initial_value: Starting text value.
            max_length: Maximum input length.
            uppercase: Force uppercase input (useful for ICAO codes).
            placeholder: Placeholder text when empty.
            on_change: Callback when text changes.
            on_submit: Callback when Enter is pressed.
        """
        super().__init__(widget_id, label, on_change, on_submit)
        self._value = initial_value
        self.max_length = max_length
        self.uppercase = uppercase
        self.placeholder = placeholder

    def activate(self) -> None:
        """Activate and enter edit mode."""
        super().activate()
        self.state = WidgetState.EDITING
        self._speak(f"{self.label}. Type to enter text.")

    def handle_key(self, key: int, unicode: str) -> bool:
        """Handle key input.

        Args:
            key: pygame key code.
            unicode: Unicode character.

        Returns:
            True if key was consumed.
        """
        if self.state != WidgetState.EDITING:
            return False

        if pygame is None:
            return False

        # Enter - submit
        if key == pygame.K_RETURN:
            self._play_click("button")
            if self._value:
                self._speak(f"Entered: {self._value}")
            self._emit_submit()
            return True

        # Escape - cancel (clear and announce)
        if key == pygame.K_ESCAPE:
            self._play_click("switch")
            old_value = self._value
            self._value = ""
            if old_value:
                self._speak("Cleared")
            self._emit_change()
            return True

        # Backspace - delete last character
        if key == pygame.K_BACKSPACE:
            if self._value:
                deleted = self._value[-1]
                self._value = self._value[:-1]
                self._play_click("knob")
                self._speak(f"Deleted {self._spell_char(deleted)}")
                self._emit_change()
            return True

        # Delete - same as backspace
        if key == pygame.K_DELETE:
            if self._value:
                deleted = self._value[-1]
                self._value = self._value[:-1]
                self._play_click("knob")
                self._speak(f"Deleted {self._spell_char(deleted)}")
                self._emit_change()
            return True

        # Arrow keys - ignore (let parent handle navigation)
        if key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT):
            return False

        # Printable character
        if unicode and len(unicode) == 1 and unicode.isprintable():
            if len(self._value) < self.max_length:
                char = unicode.upper() if self.uppercase else unicode
                self._value += char
                self._play_click("knob")
                self._speak(self._spell_char(char))
                self._emit_change()
            else:
                self._speak("Maximum length reached")
            return True

        return False

    def get_value(self) -> str:
        """Get current text value.

        Returns:
            Current text string.
        """
        return self._value

    def set_value(self, value: Any) -> None:
        """Set text value.

        Args:
            value: New text value.
        """
        if isinstance(value, str):
            self._value = value[: self.max_length]
            if self.uppercase:
                self._value = self._value.upper()

    def get_display_text(self) -> str:
        """Get display text.

        Returns:
            Current value or placeholder.
        """
        if self._value:
            return self._value
        return self.placeholder or "empty"

    def _spell_char(self, char: str) -> str:
        """Get TTS-friendly spelling of a character.

        Uses NATO phonetic alphabet for letters.

        Args:
            char: Single character.

        Returns:
            Speakable representation.
        """
        # NATO phonetic alphabet
        nato = {
            "A": "Alpha",
            "B": "Bravo",
            "C": "Charlie",
            "D": "Delta",
            "E": "Echo",
            "F": "Foxtrot",
            "G": "Golf",
            "H": "Hotel",
            "I": "India",
            "J": "Juliet",
            "K": "Kilo",
            "L": "Lima",
            "M": "Mike",
            "N": "November",
            "O": "Oscar",
            "P": "Papa",
            "Q": "Quebec",
            "R": "Romeo",
            "S": "Sierra",
            "T": "Tango",
            "U": "Uniform",
            "V": "Victor",
            "W": "Whiskey",
            "X": "X-ray",
            "Y": "Yankee",
            "Z": "Zulu",
        }

        upper = char.upper()
        if upper in nato:
            return nato[upper]
        if char.isdigit():
            # Pronounce digits individually
            digit_words = {
                "0": "Zero",
                "1": "One",
                "2": "Two",
                "3": "Three",
                "4": "Four",
                "5": "Five",
                "6": "Six",
                "7": "Seven",
                "8": "Eight",
                "9": "Niner",  # Aviation pronunciation
            }
            return digit_words.get(char, char)
        if char == " ":
            return "Space"
        if char == "-":
            return "Dash"
        if char == ".":
            return "Point"
        if char == "/":
            return "Slash"
        return char

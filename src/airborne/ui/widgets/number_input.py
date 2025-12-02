"""Number input widget for audio-accessible interfaces.

This widget allows typing numeric values with validation:
- Type digits to build a number
- Backspace to delete last digit
- Enter to submit
- Escape to cancel

Typical usage:
    widget = NumberInputWidget(
        widget_id="passengers",
        label="Passengers",
        min_value=0,
        max_value=4,
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


class NumberInputWidget(Widget):
    """Number input widget with validation.

    Allows typing a numeric value within a specified range.
    Navigate with digits to build the number.

    Attributes:
        min_value: Minimum allowed value.
        max_value: Maximum allowed value.
        allow_decimal: Whether decimal values are allowed.
    """

    def __init__(
        self,
        widget_id: str,
        label: str,
        min_value: int | float = 0,
        max_value: int | float = 100,
        default_value: int | float | None = None,
        allow_decimal: bool = False,
        unit: str = "",
        on_change: Callable[[Any], None] | None = None,
        on_submit: Callable[[Any], None] | None = None,
    ) -> None:
        """Initialize number input widget.

        Args:
            widget_id: Unique identifier.
            label: Label for TTS announcements.
            min_value: Minimum allowed value.
            max_value: Maximum allowed value.
            default_value: Initial value (defaults to min_value).
            allow_decimal: Whether to allow decimal values.
            unit: Unit label for display (e.g., "gallons", "passengers").
            on_change: Callback when selection changes.
            on_submit: Callback when selection is submitted.
        """
        super().__init__(widget_id, label, on_change, on_submit)
        self.min_value = min_value
        self.max_value = max_value
        self.allow_decimal = allow_decimal
        self.unit = unit

        self._input_buffer = ""
        self._value: int | float | None = default_value if default_value is not None else None
        self._has_decimal = False

    def activate(self) -> None:
        """Activate and enter edit mode."""
        super().activate()
        self.state = WidgetState.EDITING
        self._input_buffer = ""
        self._has_decimal = False

        # Announce current value and instructions
        current = self.get_display_text()
        max_text = f"Maximum: {int(self.max_value) if not self.allow_decimal else self.max_value}"
        if self.unit:
            max_text += f" {self.unit}"
        self._speak(f"{self.label}. {current}. {max_text}. Type a number.")

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

        # Enter - submit current value
        if key == pygame.K_RETURN:
            self._play_click("button")
            if self._input_buffer:
                # Parse the input buffer
                try:
                    if self.allow_decimal:
                        value = float(self._input_buffer)
                    else:
                        value = int(self._input_buffer)

                    # Clamp to range
                    value = max(self.min_value, min(self.max_value, value))
                    self._value = value
                    self._speak(f"Set to {self._format_value(value)}")
                except ValueError:
                    self._speak("Invalid number")
                    return True
            elif self._value is not None:
                # Keep current value
                self._speak(f"Keeping {self._format_value(self._value)}")
            else:
                # No value entered, use minimum
                self._value = self.min_value
                self._speak(f"Set to {self._format_value(self._value)}")

            self._emit_submit()
            return True

        # Escape - cancel
        if key == pygame.K_ESCAPE:
            self._play_click("switch")
            self._input_buffer = ""
            self._speak("Cancelled")
            self._emit_submit()
            return True

        # Backspace - delete last character
        if key == pygame.K_BACKSPACE:
            if self._input_buffer:
                deleted = self._input_buffer[-1]
                self._input_buffer = self._input_buffer[:-1]
                if deleted == ".":
                    self._has_decimal = False
                self._play_click("knob")
                if self._input_buffer:
                    self._speak(f"Deleted. {self._input_buffer}")
                else:
                    self._speak("Cleared")
                self._emit_change()
            return True

        # Decimal point
        if unicode == "." and self.allow_decimal and not self._has_decimal:
            self._input_buffer += "."
            self._has_decimal = True
            self._play_click("knob")
            self._speak("Point")
            self._emit_change()
            return True

        # Digit - add to buffer
        if unicode and unicode.isdigit():
            # Check if adding this digit would exceed max
            test_value = self._input_buffer + unicode
            try:
                if self.allow_decimal:
                    parsed = float(test_value) if test_value != "." else 0
                else:
                    parsed = int(test_value)

                if parsed > self.max_value:
                    self._speak(f"Maximum is {int(self.max_value) if not self.allow_decimal else self.max_value}")
                    return True
            except ValueError:
                pass

            self._input_buffer += unicode
            self._play_click("knob")
            self._speak(unicode)
            self._emit_change()
            return True

        return False

    def _format_value(self, value: int | float | None) -> str:
        """Format a value for display.

        Args:
            value: Value to format.

        Returns:
            Formatted string.
        """
        if value is None:
            return "not set"

        if self.allow_decimal:
            formatted = f"{value:.1f}"
        else:
            formatted = str(int(value))

        if self.unit:
            formatted += f" {self.unit}"

        return formatted

    def get_value(self) -> int | float | None:
        """Get current value.

        Returns:
            Current numeric value or None if not set.
        """
        return self._value

    def set_value(self, value: Any) -> None:
        """Set the value.

        Args:
            value: Numeric value to set.
        """
        if value is None:
            self._value = None
        elif isinstance(value, (int, float)):
            self._value = max(self.min_value, min(self.max_value, value))
        self._input_buffer = ""

    def get_display_text(self) -> str:
        """Get display text.

        Returns:
            Formatted value or "not set".
        """
        return self._format_value(self._value)

    def get_input_buffer(self) -> str:
        """Get current input buffer.

        Returns:
            Current input string.
        """
        return self._input_buffer

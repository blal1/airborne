"""Slider widget for numeric value selection.

This widget provides audio-accessible slider functionality:
- Left/Right arrows to decrease/increase value
- Up/Down arrows for larger steps
- Direct number input
- TTS feedback for value changes

Typical usage:
    widget = SliderWidget(
        widget_id="rate",
        label="Speech Rate",
        min_value=100,
        max_value=300,
        step=10,
        initial_value=180,
        unit="words per minute",
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


class SliderWidget(Widget):
    """Numeric slider widget with audio feedback.

    Navigate with arrow keys to adjust value.
    Left/Right for small steps, Up/Down for large steps.

    Attributes:
        value: Current numeric value.
        min_value: Minimum allowed value.
        max_value: Maximum allowed value.
        step: Small step increment (Left/Right arrows).
        large_step: Large step increment (Up/Down arrows).
    """

    def __init__(
        self,
        widget_id: str,
        label: str,
        min_value: int = 0,
        max_value: int = 100,
        step: int = 1,
        large_step: int | None = None,
        initial_value: int | None = None,
        unit: str = "",
        on_change: Callable[[Any], None] | None = None,
        on_submit: Callable[[Any], None] | None = None,
    ) -> None:
        """Initialize slider widget.

        Args:
            widget_id: Unique identifier.
            label: Label for TTS announcements.
            min_value: Minimum value.
            max_value: Maximum value.
            step: Small step size for Left/Right.
            large_step: Large step size for Up/Down (default: 10x step).
            initial_value: Starting value (default: min_value).
            unit: Unit label for TTS (e.g., "percent", "WPM").
            on_change: Callback when value changes.
            on_submit: Callback when Enter is pressed.
        """
        super().__init__(widget_id, label, on_change, on_submit)
        self.min_value = min_value
        self.max_value = max_value
        self.step = step
        self.large_step = large_step if large_step is not None else step * 10
        self.unit = unit
        self._value = initial_value if initial_value is not None else min_value

    def activate(self) -> None:
        """Activate the widget."""
        super().activate()
        self._speak(f"{self.label}: {self._format_value()}. Use arrows to adjust.")

    def handle_key(self, key: int, unicode: str) -> bool:
        """Handle key input.

        Args:
            key: pygame key code.
            unicode: Unicode character.

        Returns:
            True if key was consumed.
        """
        if self.state != WidgetState.ACTIVE:
            return False

        if pygame is None:
            return False

        # Right arrow - increase by small step
        if key == pygame.K_RIGHT:
            self._adjust(self.step)
            return True

        # Left arrow - decrease by small step
        if key == pygame.K_LEFT:
            self._adjust(-self.step)
            return True

        # Up arrow - increase by large step
        if key == pygame.K_UP:
            self._adjust(self.large_step)
            return True

        # Down arrow - decrease by large step
        if key == pygame.K_DOWN:
            self._adjust(-self.large_step)
            return True

        # Home - go to minimum
        if key == pygame.K_HOME:
            if self._value != self.min_value:
                self._value = self.min_value
                self._play_click("switch")
                self._speak(f"Minimum: {self._format_value()}")
                self._emit_change()
            return True

        # End - go to maximum
        if key == pygame.K_END:
            if self._value != self.max_value:
                self._value = self.max_value
                self._play_click("switch")
                self._speak(f"Maximum: {self._format_value()}")
                self._emit_change()
            return True

        # Enter - submit
        if key == pygame.K_RETURN:
            self._play_click("button")
            self._speak(f"Set to {self._format_value()}")
            self._emit_submit()
            return True

        # Escape - announce current value without changing
        if key == pygame.K_ESCAPE:
            self._speak(self._format_value())
            return True

        return False

    def _adjust(self, delta: int) -> None:
        """Adjust value by delta with bounds checking.

        Args:
            delta: Amount to change value by.
        """
        old_value = self._value
        self._value = max(self.min_value, min(self.max_value, self._value + delta))

        if self._value != old_value:
            self._play_click("knob")
            self._speak(self._format_value())
            self._emit_change()
        elif delta > 0:
            self._speak("Maximum")
        elif delta < 0:
            self._speak("Minimum")

    def _format_value(self) -> str:
        """Format value for TTS.

        Returns:
            Formatted value string.
        """
        if self.unit:
            return f"{self._value} {self.unit}"
        return str(self._value)

    def get_value(self) -> int:
        """Get current value.

        Returns:
            Current numeric value.
        """
        return self._value

    def set_value(self, value: Any) -> None:
        """Set value with bounds checking.

        Args:
            value: New value to set.
        """
        if isinstance(value, (int, float)):
            self._value = max(self.min_value, min(self.max_value, int(value)))

    def get_display_text(self) -> str:
        """Get display text.

        Returns:
            Formatted value string.
        """
        return self._format_value()

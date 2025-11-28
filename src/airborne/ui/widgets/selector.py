"""Selector widget for choosing from a list of options.

This widget provides audio-accessible option selection:
- Up/Down arrows to navigate options
- Enter to select
- TTS announces each option

Typical usage:
    widget = SelectorWidget(
        widget_id="voice",
        label="Voice",
        options=[
            ("samantha", "Samantha (English)"),
            ("alex", "Alex (English)"),
            ("tom", "Tom (English)"),
        ],
    )
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

from airborne.ui.widgets.base import Widget, WidgetState

logger = logging.getLogger(__name__)


@dataclass
class SelectOption:
    """An option for the selector widget.

    Attributes:
        value: The actual value returned when selected.
        display: Human-readable display text.
        data: Optional additional data.
    """

    value: str
    display: str
    data: dict[str, Any] | None = None


class SelectorWidget(Widget):
    """Option selector widget with audio feedback.

    Navigate options with Up/Down arrows, select with Enter.

    Attributes:
        options: List of available options.
        selected_index: Currently highlighted option index.
    """

    def __init__(
        self,
        widget_id: str,
        label: str,
        options: list[tuple[str, str]] | list[SelectOption] | None = None,
        initial_value: str | None = None,
        on_change: Callable[[Any], None] | None = None,
        on_submit: Callable[[Any], None] | None = None,
        on_preview: Callable[[str], None] | None = None,
    ) -> None:
        """Initialize selector widget.

        Args:
            widget_id: Unique identifier.
            label: Label for TTS announcements.
            options: List of (value, display) tuples or SelectOption objects.
            initial_value: Value to pre-select.
            on_change: Callback when selection changes.
            on_submit: Callback when Enter is pressed.
            on_preview: Callback to preview an option (e.g., play voice sample).
        """
        super().__init__(widget_id, label, on_change, on_submit)
        self._on_preview = on_preview
        self._options: list[SelectOption] = []
        self._selected_index = 0

        if options:
            self.set_options(options)

        if initial_value:
            self.set_value(initial_value)

    def set_options(self, options: list[tuple[str, str]] | list[SelectOption]) -> None:
        """Set available options.

        Args:
            options: List of (value, display) tuples or SelectOption objects.
        """
        self._options = []
        for opt in options:
            if isinstance(opt, SelectOption):
                self._options.append(opt)
            elif isinstance(opt, tuple) and len(opt) >= 2:
                self._options.append(SelectOption(value=opt[0], display=opt[1]))

        # Reset selection if out of bounds
        if self._selected_index >= len(self._options):
            self._selected_index = 0

    def activate(self) -> None:
        """Activate the widget."""
        super().activate()
        if self._options:
            opt = self._options[self._selected_index]
            total = len(self._options)
            self._speak(f"{self.label}: {opt.display}. {total} options. Use arrows to browse.")
        else:
            self._speak(f"{self.label}: No options available.")

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

        if not self._options:
            return False

        # Down arrow - next option
        if key == pygame.K_DOWN:
            self._play_click("knob")
            if self._selected_index < len(self._options) - 1:
                self._selected_index += 1
            else:
                self._selected_index = 0  # Wrap to top
            self._announce_current()
            self._emit_change()
            return True

        # Up arrow - previous option
        if key == pygame.K_UP:
            self._play_click("knob")
            if self._selected_index > 0:
                self._selected_index -= 1
            else:
                self._selected_index = len(self._options) - 1  # Wrap to bottom
            self._announce_current()
            self._emit_change()
            return True

        # Right arrow - preview current option
        if key == pygame.K_RIGHT:
            if self._on_preview:
                self._play_click("switch")
                opt = self._options[self._selected_index]
                self._on_preview(opt.value)
            return True

        # Enter - select current option
        if key == pygame.K_RETURN:
            self._play_click("button")
            opt = self._options[self._selected_index]
            self._speak(f"Selected: {opt.display}")
            self._emit_submit()
            return True

        # Home - go to first option
        if key == pygame.K_HOME:
            if self._selected_index != 0:
                self._play_click("switch")
                self._selected_index = 0
                self._announce_current()
                self._emit_change()
            return True

        # End - go to last option
        if key == pygame.K_END:
            last = len(self._options) - 1
            if self._selected_index != last:
                self._play_click("switch")
                self._selected_index = last
                self._announce_current()
                self._emit_change()
            return True

        # Escape - announce current without changing
        if key == pygame.K_ESCAPE:
            self._announce_current()
            return True

        # Letter keys - jump to option starting with that letter
        if unicode and len(unicode) == 1 and unicode.isalpha():
            letter = unicode.lower()
            # Find next option starting with this letter
            for i in range(len(self._options)):
                idx = (self._selected_index + 1 + i) % len(self._options)
                if self._options[idx].display.lower().startswith(letter):
                    self._play_click("knob")
                    self._selected_index = idx
                    self._announce_current()
                    self._emit_change()
                    return True
            return True  # Consume but don't navigate

        return False

    def _announce_current(self) -> None:
        """Announce currently selected option."""
        if 0 <= self._selected_index < len(self._options):
            opt = self._options[self._selected_index]
            position = self._selected_index + 1
            total = len(self._options)
            self._speak(f"{position} of {total}: {opt.display}")

    def get_value(self) -> str | None:
        """Get currently selected value.

        Returns:
            Selected value or None if no options.
        """
        if 0 <= self._selected_index < len(self._options):
            return self._options[self._selected_index].value
        return None

    def set_value(self, value: Any) -> None:
        """Set selection by value.

        Args:
            value: Value to select.
        """
        if not isinstance(value, str):
            return

        for i, opt in enumerate(self._options):
            if opt.value == value:
                self._selected_index = i
                return

    def get_display_text(self) -> str:
        """Get display text of current selection.

        Returns:
            Display text or "not set".
        """
        if 0 <= self._selected_index < len(self._options):
            return self._options[self._selected_index].display
        return "not set"

    def get_selected_option(self) -> SelectOption | None:
        """Get the full SelectOption object for current selection.

        Returns:
            SelectOption or None.
        """
        if 0 <= self._selected_index < len(self._options):
            return self._options[self._selected_index]
        return None

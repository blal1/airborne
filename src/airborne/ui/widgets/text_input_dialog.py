"""Text input dialog for modal text entry.

This module provides a simple modal text input dialog that can be
displayed on top of the main game to accept text input.

Typical usage:
    dialog = TextInputDialog(
        label="Enter ATC command",
        on_submit=lambda text: process_command(text),
        on_cancel=lambda: print("Cancelled"),
    )
    dialog.show()

    # In update loop:
    dialog.handle_key(key, unicode, mods)
"""

import logging
from collections.abc import Callable

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

from airborne.ui.widgets.text_input import TextInputWidget

logger = logging.getLogger(__name__)


class TextInputDialog:
    """Modal text input dialog.

    Wraps a TextInputWidget to provide a simple modal dialog
    for entering text. Calls on_submit when Enter is pressed,
    or on_cancel when Escape is pressed.

    Attributes:
        is_visible: Whether the dialog is currently shown.
    """

    def __init__(
        self,
        label: str = "Enter text",
        on_submit: Callable[[str], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        use_phonetic: bool = False,
        max_length: int = 200,
    ) -> None:
        """Initialize text input dialog.

        Args:
            label: Label for TTS announcement.
            on_submit: Callback when Enter is pressed with text.
            on_cancel: Callback when Escape is pressed.
            use_phonetic: Use NATO phonetic alphabet for letters.
            max_length: Maximum input length.
        """
        self._label = label
        self._on_submit = on_submit
        self._on_cancel = on_cancel
        self._use_phonetic = use_phonetic
        self._max_length = max_length

        self._widget: TextInputWidget | None = None
        self.is_visible = False

        # Audio callbacks
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
            click: Function to play click sound.
        """
        self._speak_callback = speak
        self._click_callback = click

    def show(self) -> None:
        """Show the dialog and start accepting input."""
        self._widget = TextInputWidget(
            widget_id="text_input_dialog",
            label=self._label,
            enable_completion=False,
            use_phonetic=self._use_phonetic,
            max_length=self._max_length,
            on_submit=self._handle_submit,
        )
        self._widget.set_audio_callbacks(
            speak=self._speak_callback,
            click=self._click_callback,
        )
        self._widget.activate()
        self.is_visible = True

        if self._speak_callback:
            self._speak_callback(f"{self._label}. Type your message, then press Enter.")

    def hide(self) -> None:
        """Hide the dialog."""
        self.is_visible = False
        self._widget = None

    def handle_key(self, key: int, unicode: str, mods: int = 0) -> bool:
        """Handle key input.

        Args:
            key: pygame key code.
            unicode: Unicode character.
            mods: Modifier keys state.

        Returns:
            True if key was consumed.
        """
        if not self.is_visible or not self._widget:
            return False

        if pygame is None:
            return False

        # Escape cancels the dialog
        if key == pygame.K_ESCAPE:
            self.hide()
            if self._on_cancel:
                self._on_cancel()
            return True

        # Pass to widget
        return self._widget.handle_key(key, unicode, mods)

    def _handle_submit(self, event: object) -> None:
        """Handle widget submit event."""
        if not self._widget:
            return

        text = self._widget.get_query()
        self.hide()

        if text and self._on_submit:
            self._on_submit(text)

    def get_text(self) -> str:
        """Get current text.

        Returns:
            Current text in the input.
        """
        if self._widget:
            return self._widget.get_query()
        return ""

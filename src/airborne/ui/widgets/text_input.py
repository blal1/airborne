"""Text input widget for audio-accessible interfaces.

This widget provides text input with optional autocomplete suggestions:
- Type to enter text or filter suggestions
- Up/Down arrows to navigate suggestions (when completion enabled)
- Left/Right arrows move cursor within text
- Home/End go to beginning/end of text
- Ctrl+Left/Right move word by word
- Enter to submit
- TTS announces each character or suggestion

Typical usage:
    # Simple text input (no completion):
    widget = TextInputWidget(
        widget_id="atc_text",
        label="ATC Message",
        enable_completion=False,
        use_phonetic=False,  # Use real letters (a, b, c)
        on_submit=lambda e: print(f"Text: {e.value}"),
    )

    # With autocomplete:
    from airborne.airports.airport_index import get_airport_index

    index = get_airport_index()

    def search_airports(query: str) -> list[tuple[str, str]]:
        results = index.search(query, limit=5)
        return [(a.icao, a.display_name()) for a in results]

    widget = TextInputWidget(
        widget_id="departure",
        label="Departure Airport",
        search_func=search_airports,
        on_submit=lambda e: print(f"Selected: {e.value}"),
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

from airborne.core.i18n import t
from airborne.ui.widgets.base import Widget, WidgetState

logger = logging.getLogger(__name__)


@dataclass
class SuggestionItem:
    """A suggestion item for autocomplete.

    Attributes:
        value: The actual value to return when selected.
        display: Human-readable display text.
        data: Optional additional data.
    """

    value: str
    display: str
    data: dict[str, Any] | None = None


class TextInputWidget(Widget):
    """Text input widget with optional autocomplete suggestions.

    Provides full-featured text input with cursor navigation,
    optional autocomplete suggestions, and TTS feedback.

    Attributes:
        suggestions: Current list of suggestions (when completion enabled).
        selected_index: Currently highlighted suggestion index.
    """

    def __init__(
        self,
        widget_id: str,
        label: str,
        search_func: Callable[[str], list[tuple[str, str]]] | None = None,
        min_query_length: int = 1,
        max_suggestions: int = 10,
        uppercase: bool = False,
        enable_completion: bool = True,
        use_phonetic: bool = True,
        max_length: int = 200,
        on_change: Callable[[Any], None] | None = None,
        on_submit: Callable[[Any], None] | None = None,
    ) -> None:
        """Initialize text input widget.

        Args:
            widget_id: Unique identifier.
            label: Label for TTS announcements.
            search_func: Function that takes query string and returns
                        list of (value, display) tuples. Optional if
                        enable_completion is False.
            min_query_length: Minimum characters before searching.
            max_suggestions: Maximum suggestions to show.
            uppercase: Force uppercase input.
            enable_completion: If False, disables suggestions and up/down nav.
            use_phonetic: If True, use NATO phonetic alphabet for letter TTS.
                         If False, use real letters (a, b, c).
            max_length: Maximum input length.
            on_change: Callback when selection changes.
            on_submit: Callback when selection is submitted.
        """
        super().__init__(widget_id, label, on_change, on_submit)
        self._search_func = search_func
        self.min_query_length = min_query_length
        self.max_suggestions = max_suggestions
        self.uppercase = uppercase
        self.enable_completion = enable_completion
        self.use_phonetic = use_phonetic
        self.max_length = max_length

        self._query = ""
        self._cursor_pos = 0  # Cursor position within _query
        self._suggestions: list[SuggestionItem] = []
        self._selected_index = -1  # -1 means in text input mode
        self._selected_value: str | None = None  # Final selected value

    def activate(self) -> None:
        """Activate and enter edit mode."""
        super().activate()
        self.state = WidgetState.EDITING
        if self._selected_value:
            self._speak(f"{self.label}: {self._selected_value}")
        else:
            self._speak(f"{self.label}. {t('widget.text_input.type_to_search')}")

    def handle_key(self, key: int, unicode: str, mods: int = 0) -> bool:
        """Handle key input.

        Args:
            key: pygame key code.
            unicode: Unicode character.
            mods: Modifier keys state (pygame.key.get_mods()).

        Returns:
            True if key was consumed.
        """
        if self.state != WidgetState.EDITING:
            return False

        if pygame is None:
            return False

        # Get modifier state
        ctrl = mods & pygame.KMOD_CTRL

        # Down arrow - move to suggestions or next suggestion
        if key == pygame.K_DOWN:
            if self.enable_completion and self._suggestions:
                self._play_click("knob")
                if self._selected_index < len(self._suggestions) - 1:
                    self._selected_index += 1
                else:
                    self._selected_index = 0  # Wrap to top
                self._announce_current_suggestion()
            # If completion disabled, do nothing
            return True

        # Up arrow - move to previous suggestion
        if key == pygame.K_UP:
            if self.enable_completion and self._suggestions:
                self._play_click("knob")
                if self._selected_index > 0:
                    self._selected_index -= 1
                else:
                    self._selected_index = len(self._suggestions) - 1  # Wrap to bottom
                self._announce_current_suggestion()
            # If completion disabled, do nothing
            return True

        # Left arrow - move cursor left (with Ctrl: word by word)
        if key == pygame.K_LEFT:
            if self._cursor_pos > 0:
                self._play_click("knob")
                if ctrl:
                    # Move to start of previous word
                    self._cursor_pos = self._find_word_start(self._cursor_pos - 1)
                else:
                    self._cursor_pos -= 1
                self._announce_cursor_position()
            return True

        # Right arrow - move cursor right (with Ctrl: word by word)
        if key == pygame.K_RIGHT:
            if self._cursor_pos < len(self._query):
                self._play_click("knob")
                if ctrl:
                    # Move to end of next word
                    self._cursor_pos = self._find_word_end(self._cursor_pos + 1)
                else:
                    self._cursor_pos += 1
                self._announce_cursor_position()
            return True

        # Home - go to beginning
        if key == pygame.K_HOME:
            if self._cursor_pos > 0:
                self._play_click("knob")
                self._cursor_pos = 0
                self._speak(t("widget.text_input.beginning"))
            return True

        # End - go to end
        if key == pygame.K_END:
            if self._cursor_pos < len(self._query):
                self._play_click("knob")
                self._cursor_pos = len(self._query)
                self._speak(t("widget.text_input.end"))
            return True

        # Enter - select current suggestion or submit query
        if key == pygame.K_RETURN:
            self._play_click("button")
            if self.enable_completion and self._selected_index >= 0 and self._selected_index < len(self._suggestions):
                # Select the highlighted suggestion
                selected = self._suggestions[self._selected_index]
                self._selected_value = selected.value
                self._speak(f"{t('widget.text_input.selected')}: {selected.display}")
                self._emit_submit()
            elif self._query:
                # No suggestion selected, submit the raw query
                self._selected_value = self._query
                self._speak(f"{t('widget.text_input.entered')}: {self._query}")
                self._emit_submit()
            return True

        # Escape - clear and go back to text input
        if key == pygame.K_ESCAPE:
            self._play_click("switch")
            if self.enable_completion and self._selected_index >= 0:
                # Just go back to text input mode
                self._selected_index = -1
                self._speak(t("widget.text_input.back_to_input"))
            else:
                # Clear the query
                self._query = ""
                self._cursor_pos = 0
                self._suggestions = []
                self._selected_value = None
                self._speak(t("widget.text_input.cleared"))
                self._emit_change()
            return True

        # Backspace - delete character before cursor
        if key == pygame.K_BACKSPACE:
            if self._cursor_pos > 0:
                deleted = self._query[self._cursor_pos - 1]
                self._query = self._query[:self._cursor_pos - 1] + self._query[self._cursor_pos:]
                self._cursor_pos -= 1
                self._play_click("knob")
                self._speak(f"{t('widget.text_input.deleted')} {self._spell_char(deleted)}")
                self._update_suggestions()
                self._emit_change()
            return True

        # Delete - delete character at cursor
        if key == pygame.K_DELETE:
            if self._cursor_pos < len(self._query):
                deleted = self._query[self._cursor_pos]
                self._query = self._query[:self._cursor_pos] + self._query[self._cursor_pos + 1:]
                self._play_click("knob")
                self._speak(f"{t('widget.text_input.deleted')} {self._spell_char(deleted)}")
                self._update_suggestions()
                self._emit_change()
            return True

        # Tab - autocomplete with first suggestion (only if completion enabled)
        if key == pygame.K_TAB:
            if self.enable_completion and self._suggestions:
                self._play_click("knob")
                self._selected_index = 0
                self._announce_current_suggestion()
            return True

        # Printable character - insert at cursor position
        if unicode and len(unicode) == 1 and unicode.isprintable():
            if len(self._query) < self.max_length:
                char = unicode.upper() if self.uppercase else unicode
                self._query = self._query[:self._cursor_pos] + char + self._query[self._cursor_pos:]
                self._cursor_pos += 1
                self._selected_index = -1  # Go back to text input mode
                self._play_click("knob")
                self._speak(self._spell_char(char))
                self._update_suggestions()
                self._emit_change()
            else:
                self._speak(t("widget.text_input.max_length"))
            return True

        return False

    def _find_word_start(self, pos: int) -> int:
        """Find the start of the word at or before position.

        Args:
            pos: Starting position.

        Returns:
            Position of word start.
        """
        if pos <= 0:
            return 0

        # Skip any trailing spaces
        while pos > 0 and self._query[pos] == " ":
            pos -= 1

        # Find start of current word
        while pos > 0 and self._query[pos - 1] != " ":
            pos -= 1

        return pos

    def _find_word_end(self, pos: int) -> int:
        """Find the end of the word at or after position.

        Args:
            pos: Starting position.

        Returns:
            Position after word end.
        """
        length = len(self._query)
        if pos >= length:
            return length

        # Skip any leading spaces
        while pos < length and self._query[pos] == " ":
            pos += 1

        # Find end of current word
        while pos < length and self._query[pos] != " ":
            pos += 1

        return pos

    def _announce_cursor_position(self) -> None:
        """Announce the character at cursor position."""
        if self._cursor_pos < len(self._query):
            char = self._query[self._cursor_pos]
            self._speak(self._spell_char(char))
        else:
            self._speak(t("widget.text_input.end"))

    def _update_suggestions(self) -> None:
        """Update suggestions based on current query."""
        # Skip if completion is disabled
        if not self.enable_completion or not self._search_func:
            self._suggestions = []
            return

        if len(self._query) < self.min_query_length:
            self._suggestions = []
            return

        try:
            results = self._search_func(self._query)
            self._suggestions = [
                SuggestionItem(value=value, display=display)
                for value, display in results[: self.max_suggestions]
            ]

            # Announce number of results
            count = len(self._suggestions)
            if count == 0:
                self._speak(t("widget.text_input.no_matches"))
            elif count == 1:
                self._speak(f"{t('widget.text_input.one_match')}: {self._suggestions[0].display}")
                self._selected_index = 0
            else:
                self._speak(f"{count} {t('widget.text_input.matches')}. {t('widget.text_input.use_arrows')}")
                self._selected_index = 0

        except Exception as e:
            logger.error("Search failed: %s", e)
            self._suggestions = []

    def _announce_current_suggestion(self) -> None:
        """Announce the currently selected suggestion."""
        if 0 <= self._selected_index < len(self._suggestions):
            suggestion = self._suggestions[self._selected_index]
            position = self._selected_index + 1
            total = len(self._suggestions)
            self._speak(f"{position} {t('widget.text_input.of')} {total}: {suggestion.display}")

    def get_value(self) -> str | None:
        """Get selected value.

        Returns:
            Selected value string or None if nothing selected.
        """
        return self._selected_value

    def set_value(self, value: Any) -> None:
        """Set the selected value.

        Args:
            value: Value to set.
        """
        if isinstance(value, str):
            self._selected_value = value
            self._query = value[:self.max_length]
            self._cursor_pos = len(self._query)

    def get_display_text(self) -> str:
        """Get display text.

        Returns:
            Selected value, query, or empty indicator.
        """
        if self._selected_value:
            return self._selected_value
        if self._query:
            return self._query
        return "not set"

    def get_query(self) -> str:
        """Get current search query.

        Returns:
            Current query string.
        """
        return self._query

    def get_cursor_pos(self) -> int:
        """Get current cursor position.

        Returns:
            Cursor position in the query string.
        """
        return self._cursor_pos

    def clear(self) -> None:
        """Clear the input and reset state."""
        self._query = ""
        self._cursor_pos = 0
        self._suggestions = []
        self._selected_index = -1
        self._selected_value = None

    def get_suggestions(self) -> list[SuggestionItem]:
        """Get current suggestions.

        Returns:
            List of current suggestions.
        """
        return self._suggestions.copy()

    def _spell_char(self, char: str) -> str:
        """Get TTS-friendly spelling of a character.

        Args:
            char: Single character.

        Returns:
            Speakable representation.
        """
        upper = char.upper()

        # Use phonetic alphabet or real letters based on setting
        if upper.isalpha():
            if self.use_phonetic:
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
                return nato.get(upper, char)
            else:
                # Use real letter (just return the letter)
                return upper

        if char.isdigit():
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
                "9": "Niner" if self.use_phonetic else "Nine",
            }
            return digit_words.get(char, char)
        if char == " ":
            return "Space"
        if char == "-":
            return "Dash"
        if char == ".":
            return "Point"
        if char == ",":
            return "Comma"
        if char == "'":
            return "Apostrophe"
        return char

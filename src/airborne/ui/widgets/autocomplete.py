"""Autocomplete widget for audio-accessible interfaces.

This widget combines text input with a suggestions list:
- Type to filter suggestions
- Up/Down arrows to navigate suggestions
- Enter to select suggestion
- TTS announces each suggestion

Typical usage:
    from airborne.airports.airport_index import get_airport_index

    index = get_airport_index()

    def search_airports(query: str) -> list[tuple[str, str]]:
        results = index.search(query, limit=5)
        return [(a.icao, a.display_name()) for a in results]

    widget = AutocompleteWidget(
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


class AutocompleteWidget(Widget):
    """Autocomplete widget with search suggestions.

    Combines text input with a filterable suggestions list.
    Navigate with arrow keys, select with Enter.

    Attributes:
        suggestions: Current list of suggestions.
        selected_index: Currently highlighted suggestion index.
    """

    def __init__(
        self,
        widget_id: str,
        label: str,
        search_func: Callable[[str], list[tuple[str, str]]],
        min_query_length: int = 1,
        max_suggestions: int = 10,
        uppercase: bool = False,
        on_change: Callable[[Any], None] | None = None,
        on_submit: Callable[[Any], None] | None = None,
    ) -> None:
        """Initialize autocomplete widget.

        Args:
            widget_id: Unique identifier.
            label: Label for TTS announcements.
            search_func: Function that takes query string and returns
                        list of (value, display) tuples.
            min_query_length: Minimum characters before searching.
            max_suggestions: Maximum suggestions to show.
            uppercase: Force uppercase input.
            on_change: Callback when selection changes.
            on_submit: Callback when selection is submitted.
        """
        super().__init__(widget_id, label, on_change, on_submit)
        self._search_func = search_func
        self.min_query_length = min_query_length
        self.max_suggestions = max_suggestions
        self.uppercase = uppercase

        self._query = ""
        self._suggestions: list[SuggestionItem] = []
        self._selected_index = -1  # -1 means in text input mode
        self._selected_value: str | None = None  # Final selected value

    def activate(self) -> None:
        """Activate and enter edit mode."""
        super().activate()
        self.state = WidgetState.EDITING
        if self._selected_value:
            self._speak(f"{self.label}: {self._selected_value}. Type to change.")
        else:
            self._speak(f"{self.label}. Type to search.")

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

        # Down arrow - move to suggestions or next suggestion
        if key == pygame.K_DOWN:
            if self._suggestions:
                self._play_click("knob")
                if self._selected_index < len(self._suggestions) - 1:
                    self._selected_index += 1
                else:
                    self._selected_index = 0  # Wrap to top
                self._announce_current_suggestion()
            return True

        # Up arrow - move to previous suggestion
        if key == pygame.K_UP:
            if self._suggestions:
                self._play_click("knob")
                if self._selected_index > 0:
                    self._selected_index -= 1
                else:
                    self._selected_index = len(self._suggestions) - 1  # Wrap to bottom
                self._announce_current_suggestion()
            return True

        # Enter - select current suggestion or submit query
        if key == pygame.K_RETURN:
            self._play_click("button")
            if self._selected_index >= 0 and self._selected_index < len(self._suggestions):
                # Select the highlighted suggestion
                selected = self._suggestions[self._selected_index]
                self._selected_value = selected.value
                self._speak(f"Selected: {selected.display}")
                self._emit_submit()
            elif self._query:
                # No suggestion selected, submit the raw query
                self._selected_value = self._query
                self._speak(f"Entered: {self._query}")
                self._emit_submit()
            return True

        # Escape - clear and go back to text input
        if key == pygame.K_ESCAPE:
            self._play_click("switch")
            if self._selected_index >= 0:
                # Just go back to text input mode
                self._selected_index = -1
                self._speak("Back to text input")
            else:
                # Clear the query
                self._query = ""
                self._suggestions = []
                self._selected_value = None
                self._speak("Cleared")
                self._emit_change()
            return True

        # Backspace - delete character
        if key == pygame.K_BACKSPACE:
            if self._query:
                deleted = self._query[-1]
                self._query = self._query[:-1]
                self._play_click("knob")
                self._speak(f"Deleted {self._spell_char(deleted)}")
                self._update_suggestions()
                self._emit_change()
            return True

        # Tab - autocomplete with first suggestion
        if key == pygame.K_TAB:
            if self._suggestions:
                self._play_click("knob")
                self._selected_index = 0
                self._announce_current_suggestion()
            return True

        # Left/Right arrows - let parent handle
        if key in (pygame.K_LEFT, pygame.K_RIGHT):
            return False

        # Printable character - add to query
        if unicode and len(unicode) == 1 and unicode.isprintable():
            char = unicode.upper() if self.uppercase else unicode
            self._query += char
            self._selected_index = -1  # Go back to text input mode
            self._play_click("knob")
            self._speak(self._spell_char(char))
            self._update_suggestions()
            self._emit_change()
            return True

        return False

    def _update_suggestions(self) -> None:
        """Update suggestions based on current query."""
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
                self._speak("No matches")
            elif count == 1:
                self._speak(f"1 match: {self._suggestions[0].display}")
                self._selected_index = 0
            else:
                self._speak(f"{count} matches. Use arrows to browse.")
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
            self._speak(f"{position} of {total}: {suggestion.display}")

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
            self._query = value

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
                "9": "Niner",
            }
            return digit_words.get(char, char)
        if char == " ":
            return "Space"
        if char == "-":
            return "Dash"
        return char

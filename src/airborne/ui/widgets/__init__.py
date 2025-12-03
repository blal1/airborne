"""Audio-accessible UI widgets for main menu.

This package provides widgets designed for audio-only interfaces,
with TTS announcements and keyboard navigation.
"""

from airborne.ui.widgets.base import Widget, WidgetState
from airborne.ui.widgets.selector import SelectorWidget
from airborne.ui.widgets.slider import SliderWidget
from airborne.ui.widgets.text_input import SuggestionItem, TextInputWidget

# Backwards compatibility alias
AutocompleteWidget = TextInputWidget

__all__ = [
    "Widget",
    "WidgetState",
    "TextInputWidget",
    "AutocompleteWidget",  # Alias for backwards compatibility
    "SuggestionItem",
    "SliderWidget",
    "SelectorWidget",
]

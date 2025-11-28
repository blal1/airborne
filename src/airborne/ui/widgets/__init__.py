"""Audio-accessible UI widgets for main menu.

This package provides widgets designed for audio-only interfaces,
with TTS announcements and keyboard navigation.
"""

from airborne.ui.widgets.autocomplete import AutocompleteWidget
from airborne.ui.widgets.base import Widget, WidgetState
from airborne.ui.widgets.selector import SelectorWidget
from airborne.ui.widgets.slider import SliderWidget
from airborne.ui.widgets.text_input import TextInputWidget

__all__ = [
    "Widget",
    "WidgetState",
    "TextInputWidget",
    "AutocompleteWidget",
    "SliderWidget",
    "SelectorWidget",
]

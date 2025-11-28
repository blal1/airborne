"""Base menu class with audio feedback for AirBorne.

This module provides a reusable base class for audio-accessible menus.
Features:
- Arrow key navigation
- TTS announcements via cache service
- Click sounds for feedback
- Submenu support

Typical usage:
    class MyMenu(AudioMenu):
        def _build_items(self) -> list[MenuItem]:
            return [
                MenuItem("option1", "First Option", action=self._do_first),
                MenuItem("option2", "Second Option", submenu=SubMenu()),
            ]
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

from airborne.core.i18n import t
from airborne.core.resource_path import get_resource_path

logger = logging.getLogger(__name__)


@dataclass
class MenuItem:
    """A menu item definition.

    Attributes:
        item_id: Unique identifier for this item.
        label: Display text for TTS announcements.
        action: Callback function when item is selected.
        submenu: Child menu to open when selected.
        enabled: Whether this item is selectable.
        data: Additional item-specific data.
    """

    item_id: str
    label: str
    action: Callable[[], None] | None = None
    submenu: "AudioMenu | None" = None
    enabled: bool = True
    data: dict[str, Any] = field(default_factory=dict)


class AudioMenu(ABC):
    """Base class for audio-accessible menus.

    Provides navigation, TTS announcements, and click sounds.
    Subclasses implement _build_items() to define menu contents.

    Attributes:
        title: Menu title for TTS announcement.
        items: List of menu items.
        selected_index: Currently highlighted item index.
        is_open: Whether the menu is currently open.
    """

    # Sound paths
    CLICK_KNOB = "assets/sounds/aircraft/click_knob.mp3"
    CLICK_SWITCH = "assets/sounds/aircraft/click_switch.mp3"
    CLICK_BUTTON = "assets/sounds/aircraft/click_button.mp3"

    def __init__(
        self,
        title: str,
        parent: "AudioMenu | None" = None,
    ) -> None:
        """Initialize menu.

        Args:
            title: Menu title for announcements.
            parent: Parent menu (for back navigation).
        """
        self.title = title
        self.parent = parent
        self.items: list[MenuItem] = []
        self.selected_index = 0
        self.is_open = False

        # Audio callbacks (set by menu manager)
        self._speak_callback: Callable[[str], None] | None = None
        self._play_sound_callback: Callable[[str, float], None] | None = None
        self._play_audio_callback: Callable[[bytes], None] | None = None

        # TTS cache service client (set by menu manager)
        self._tts_client: Any = None

        # Current active submenu or widget
        self._active_child: AudioMenu | None = None

    def set_audio_callbacks(
        self,
        speak: Callable[[str], None] | None = None,
        play_sound: Callable[[str, float], None] | None = None,
        tts_client: Any = None,
        play_audio: Callable[[bytes], None] | None = None,
    ) -> None:
        """Set audio callback functions.

        Args:
            speak: Function to speak text via TTS.
            play_sound: Function to play sound file (path, volume).
            tts_client: TTS cache service client for async TTS.
            play_audio: Function to play raw WAV audio bytes.
        """
        self._speak_callback = speak
        self._play_sound_callback = play_sound
        self._tts_client = tts_client
        self._play_audio_callback = play_audio

    def open(self) -> None:
        """Open the menu and announce title."""
        self.items = self._build_items()
        self.selected_index = 0
        self.is_open = True
        self._active_child = None

        # Announce menu opening
        self._speak(f"{self.title}. {len(self.items)} items.")
        if self.items:
            self._announce_current_item()

    def close(self) -> None:
        """Close the menu."""
        self.is_open = False
        self._active_child = None

    def reload_translations(self) -> None:
        """Reload menu items with updated translations.

        Call this after language changes to refresh all menu text.
        Propagates up to parent menus.
        """
        # Rebuild items for this menu
        self.items = self._build_items()

        # Propagate to parent menu
        if self.parent:
            self.parent.reload_translations()

    def handle_key(self, key: int, unicode: str = "") -> bool:
        """Handle keyboard input.

        Args:
            key: pygame key code.
            unicode: Unicode character for the key.

        Returns:
            True if the key was consumed.
        """
        if not self.is_open:
            return False

        # If a child menu/widget is active, delegate to it
        if self._active_child:
            consumed = self._active_child.handle_key(key, unicode)
            if consumed:
                return True
            # Check if child closed
            if hasattr(self._active_child, "is_open") and not self._active_child.is_open:
                self._active_child = None
                self._announce_current_item()
                return True

        if pygame is None:
            return False

        # Down arrow - move to next item
        if key == pygame.K_DOWN:
            self._move_down()
            return True

        # Up arrow - move to previous item
        if key == pygame.K_UP:
            self._move_up()
            return True

        # Enter - select current item
        if key == pygame.K_RETURN:
            self._select_current()
            return True

        # Escape - close menu / go back
        if key == pygame.K_ESCAPE:
            self._go_back()
            return True

        # Home - go to first item
        if key == pygame.K_HOME:
            if self.selected_index != 0 and self.items:
                self._play_click("switch")
                self.selected_index = 0
                self._announce_current_item()
            return True

        # End - go to last item
        if key == pygame.K_END:
            last = len(self.items) - 1
            if self.selected_index != last and self.items:
                self._play_click("switch")
                self.selected_index = last
                self._announce_current_item()
            return True

        # Number keys - quick select (1-9)
        if unicode and unicode.isdigit() and unicode != "0":
            idx = int(unicode) - 1
            if 0 <= idx < len(self.items):
                self._play_click("knob")
                self.selected_index = idx
                self._select_current()
            return True

        return False

    def _move_down(self) -> None:
        """Move selection down."""
        if not self.items:
            return

        self._play_click("knob")

        # Find next enabled item
        original = self.selected_index
        while True:
            self.selected_index = (self.selected_index + 1) % len(self.items)
            if self.items[self.selected_index].enabled:
                break
            if self.selected_index == original:
                break  # All items disabled

        self._announce_current_item()

    def _move_up(self) -> None:
        """Move selection up."""
        if not self.items:
            return

        self._play_click("knob")

        # Find previous enabled item
        original = self.selected_index
        while True:
            self.selected_index = (self.selected_index - 1) % len(self.items)
            if self.items[self.selected_index].enabled:
                break
            if self.selected_index == original:
                break  # All items disabled

        self._announce_current_item()

    def _select_current(self) -> None:
        """Select the current item."""
        if not self.items:
            return

        item = self.items[self.selected_index]
        if not item.enabled:
            self._speak(t("common.disabled"))
            return

        self._play_click("button")

        # Handle submenu
        if item.submenu:
            self._active_child = item.submenu
            item.submenu.parent = self
            item.submenu.set_audio_callbacks(
                speak=self._speak_callback,
                play_sound=self._play_sound_callback,
                tts_client=self._tts_client,
                play_audio=self._play_audio_callback,
            )
            item.submenu.open()
            return

        # Handle action
        if item.action:
            item.action()

    def _go_back(self) -> None:
        """Go back to parent menu or close."""
        self._play_click("switch")

        if self.parent:
            self.close()
            self._speak(t("common.back"))
        else:
            # Top-level menu - announce we're still here
            self._speak(t("menu.main.title"))

    def _announce_current_item(self) -> None:
        """Announce currently selected item."""
        if not self.items:
            return

        item = self.items[self.selected_index]

        if item.enabled:
            self._speak(item.label)
        else:
            self._speak(f"{item.label}. Disabled.")

    def _speak(self, text: str) -> None:
        """Speak text via TTS.

        Args:
            text: Text to speak.
        """
        if self._speak_callback:
            self._speak_callback(text)
        else:
            logger.debug("TTS not available: %s", text)

    def _speak_with_voice(
        self, text: str, voice_name: str, rate: int, language: str | None = None
    ) -> None:
        """Speak text with specific voice settings (for preview).

        Args:
            text: Text to speak.
            voice_name: Platform-specific voice name.
            rate: Speech rate in WPM.
            language: Language code for voice selection.
        """
        if not self._tts_client:
            logger.debug("TTS client not available for preview: %s", text)
            return

        import asyncio

        # Get language from settings if not provided
        if language is None:
            from airborne.settings import get_tts_settings

            language = get_tts_settings().language

        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self._speak_with_voice_async(text, voice_name, rate, language))
        except Exception as e:
            logger.error("Preview TTS error: %s", e)

    async def _speak_with_voice_async(
        self, text: str, voice_name: str, rate: int, language: str | None = None
    ) -> None:
        """Async helper for speaking with specific voice settings.

        Args:
            text: Text to speak.
            voice_name: Platform-specific voice name.
            rate: Speech rate in WPM.
            language: Language code for voice selection.
        """
        if not self._tts_client:
            return

        try:
            audio_data = await self._tts_client.generate(
                text,
                voice="preview",
                rate=rate,
                voice_name=voice_name,
                language=language,
            )
            if audio_data:
                await self._play_preview_audio(audio_data)
        except Exception as e:
            logger.error("Preview generation error: %s", e)

    async def _play_preview_audio(self, audio_data: bytes) -> None:
        """Play preview audio data via callback.

        Args:
            audio_data: WAV audio bytes.
        """
        if self._play_audio_callback:
            self._play_audio_callback(audio_data)

    def _play_click(self, sound_type: str = "knob") -> None:
        """Play a click sound.

        Args:
            sound_type: Type of click ("knob", "switch", "button").
        """
        if not self._play_sound_callback:
            return

        sound_map = {
            "knob": self.CLICK_KNOB,
            "switch": self.CLICK_SWITCH,
            "button": self.CLICK_BUTTON,
        }
        sound_path = sound_map.get(sound_type, self.CLICK_KNOB)
        try:
            full_path = str(get_resource_path(sound_path))
            self._play_sound_callback(full_path, 0.7)
        except Exception as e:
            logger.warning("Failed to play click: %s", e)

    @abstractmethod
    def _build_items(self) -> list[MenuItem]:
        """Build menu items. Subclasses must implement this.

        Returns:
            List of MenuItem objects.
        """
        pass

    def get_result(self) -> Any:
        """Get menu result after closing.

        Override in subclasses to return collected data.

        Returns:
            Menu result (varies by menu type).
        """
        return None

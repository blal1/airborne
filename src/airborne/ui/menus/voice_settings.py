"""Voice settings menu for TTS configuration.

This menu allows configuring TTS voice settings for each voice category:
- UI, Cockpit, ATC, ATIS, Ground, Tower, Approach, Departure, Center
- For each category: voice selection, rate adjustment, preview

Navigation:
- Up/Down: Navigate between settings (Voice, Rate, Preview, Save)
- Left/Right: Cycle through values for the current setting
- Enter: Activate (preview or save)
- Escape: Go back

Typical usage:
    menu = VoiceSettingsMenu()
    menu.open()
"""

import logging
from collections.abc import Callable

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

from airborne.core.i18n import t
from airborne.settings import VOICE_CATEGORIES, get_tts_settings
from airborne.settings.tts_settings import (
    TTS_MODE_REALTIME,
    TTS_MODE_SELFVOICED,
)
from airborne.ui.menus.base_menu import AudioMenu, MenuItem

logger = logging.getLogger(__name__)


class VoiceCategoryMenu(AudioMenu):
    """Menu for configuring a single voice category.

    Uses left/right to cycle values, up/down to navigate settings.
    """

    # Rate options from 100 to 300 WPM in steps of 20
    RATE_OPTIONS = list(range(100, 320, 20))

    def __init__(self, category: str, parent: AudioMenu | None = None) -> None:
        """Initialize voice category menu.

        Args:
            category: Voice category name (e.g., "cockpit", "tower").
            parent: Parent menu.
        """
        category_label = t(f"voice.categories.{category}")
        super().__init__(category_label, parent)
        self.category = category
        self._voices: list[tuple[str, str]] = []  # (name, display)
        self._current_voice_index = 0
        self._current_rate = 180
        self._current_rate_index = 4  # 180 WPM default
        # Callback to notify when UI voice settings change
        self._on_ui_voice_change: Callable[[str, int], None] | None = None

    def set_on_ui_voice_change(self, callback: Callable[[str, int], None]) -> None:
        """Set callback for when UI voice settings change.

        Args:
            callback: Function(voice_name, rate) called on change.
        """
        self._on_ui_voice_change = callback

    def open(self) -> None:
        """Open the menu and load current settings."""
        # Update title for i18n
        self.title = t(f"voice.categories.{self.category}")
        # Load current settings
        settings = get_tts_settings()
        voice_settings = settings.get_voice(self.category)
        self._current_rate = voice_settings.rate

        # Find rate index
        try:
            self._current_rate_index = self.RATE_OPTIONS.index(self._current_rate)
        except ValueError:
            self._current_rate_index = 4  # Default to 180

        # Load available voices based on current language
        self._voices = self._load_voices_for_language(settings.language)

        # Find current voice in list
        current_voice = voice_settings.voice_name
        for i, (name, _) in enumerate(self._voices):
            if name == current_voice:
                self._current_voice_index = i
                break

        super().open()

    def _build_items(self) -> list[MenuItem]:
        """Build menu items."""
        current_voice_display = (
            self._voices[self._current_voice_index][1]
            if self._voices
            else t("common.none_available")
        )

        return [
            MenuItem(
                "voice",
                t("voice.voice_label", voice=current_voice_display),
            ),
            MenuItem(
                "rate",
                t("voice.rate_label", rate=self._current_rate),
            ),
            MenuItem(
                "preview",
                t("voice.preview"),
                action=self._preview_voice,
            ),
            MenuItem(
                "save",
                t("voice.save_and_back"),
                action=self._save_and_close,
            ),
        ]

    def handle_key(self, key: int, unicode: str = "") -> bool:
        """Handle keyboard input with left/right for value cycling.

        Args:
            key: pygame key code.
            unicode: Unicode character.

        Returns:
            True if key was consumed.
        """
        if not self.is_open or pygame is None:
            return False

        # Handle left/right for cycling values on voice/rate items
        current_item = self.items[self.selected_index] if self.items else None

        if current_item and current_item.item_id in ("voice", "rate"):
            if key == pygame.K_LEFT:
                self._play_click("knob")
                if current_item.item_id == "voice":
                    self._cycle_voice(-1)
                else:
                    self._cycle_rate(-1)
                return True
            elif key == pygame.K_RIGHT:
                self._play_click("knob")
                if current_item.item_id == "voice":
                    self._cycle_voice(1)
                else:
                    self._cycle_rate(1)
                return True

        # Fall back to parent handling for up/down/enter/escape
        return super().handle_key(key, unicode)

    def _load_voices_for_language(self, language: str) -> list[tuple[str, str]]:
        """Load available voices for a language from the pre-fetched cache.

        Uses voices cached during menu startup by the TTS background thread.
        Falls back to pyttsx3 if cache is empty (shouldn't happen normally).

        Args:
            language: Language code (e.g., "en", "fr").

        Returns:
            List of (voice_name, display_name) tuples.
        """
        # Try to get from cache first (pre-fetched during startup)
        from airborne.ui.menus.menu_runner import get_cached_voices

        voices = get_cached_voices(language)
        if voices:
            logger.info("Using %d cached voices for language %s", len(voices), language)
            return voices

        # Fallback to pyttsx3 if cache is empty
        logger.warning("Voice cache empty for %s, falling back to pyttsx3", language)
        voices = []

        try:
            import pyttsx3

            engine = pyttsx3.init()
            all_voices = engine.getProperty("voices")

            for voice in all_voices:
                # Get language from voice properties
                voice_langs = getattr(voice, "languages", [])
                voice_lang = voice_langs[0] if voice_langs else ""

                # Convert to string and check language match
                lang_str = str(voice_lang).lower()

                # Match language code (e.g., "en" matches "en_US", "en_GB")
                # Also match "fr" for French voices with "fr_FR", "fr_CA"
                if lang_str.startswith(language.lower()) or f"_{language}" in lang_str:
                    name = voice.name

                    # Skip voices with "(null)" in name
                    if "(null)" in name:
                        continue

                    # Create display name with language variant if available
                    if "_" in lang_str:
                        # e.g., "fr_CA" -> "Amélie (CA)"
                        variant = lang_str.split("_")[1].upper()
                        display = f"{name} ({variant})"
                    else:
                        display = name

                    voices.append((name, display))

            # Sort by display name
            voices.sort(key=lambda x: x[1])
            logger.info("Loaded %d voices via pyttsx3 for language %s", len(voices), language)

            engine.stop()

        except Exception as e:
            logger.warning("Failed to load voices via pyttsx3: %s", e)

        return voices

    def _cycle_voice(self, direction: int) -> None:
        """Cycle through available voices.

        Args:
            direction: 1 for next, -1 for previous.
        """
        if not self._voices:
            self._speak(t("common.none_available"))
            return

        self._current_voice_index = (self._current_voice_index + direction) % len(self._voices)
        voice_name, display = self._voices[self._current_voice_index]

        # Just announce the voice name, not "Voice:"
        self._speak(display)

        # Update menu item display
        self.items = self._build_items()

        # Notify if this is UI voice
        if self.category == "ui" and self._on_ui_voice_change:
            self._on_ui_voice_change(voice_name, self._current_rate)

    def _cycle_rate(self, direction: int) -> None:
        """Cycle through rate options.

        Args:
            direction: 1 for next, -1 for previous.
        """
        self._current_rate_index = (self._current_rate_index + direction) % len(self.RATE_OPTIONS)
        self._current_rate = self.RATE_OPTIONS[self._current_rate_index]

        # Just announce the WPM value, not "Rate:"
        self._speak(f"{self._current_rate}")

        # Update menu item display
        self.items = self._build_items()

        # Notify if this is UI voice
        if self.category == "ui" and self._on_ui_voice_change:
            voice_name = self._voices[self._current_voice_index][0] if self._voices else "Samantha"
            self._on_ui_voice_change(voice_name, self._current_rate)

    def _preview_voice(self) -> None:
        """Preview the current voice with a sample phrase."""
        if not self._voices:
            self._speak(t("voice.no_voice_selected"))
            return

        sample = t(f"voice.samples.{self.category}")
        voice_name = self._voices[self._current_voice_index][0]

        # Use TTS client directly with selected voice settings
        self._speak_with_voice(sample, voice_name, self._current_rate)

    def _save_and_close(self) -> None:
        """Save settings and close menu."""
        if self._voices:
            voice_name, _ = self._voices[self._current_voice_index]
            settings = get_tts_settings()
            settings.set_voice(self.category, voice_name, "apple", self._current_rate)
            settings.save()
            self._speak(t("common.saved"))

        self.close()


class VoiceSettingsMenu(AudioMenu):
    """Main voice settings menu.

    Lists all voice categories for configuration.
    """

    def __init__(self, parent: AudioMenu | None = None) -> None:
        """Initialize voice settings menu."""
        super().__init__(t("voice.title"), parent)
        self._category_menus: dict[str, VoiceCategoryMenu] = {}
        self._on_ui_voice_change: Callable[[str, int], None] | None = None
        self._current_mode: str = TTS_MODE_REALTIME

    def set_on_ui_voice_change(self, callback: Callable[[str, int], None]) -> None:
        """Set callback for when UI voice settings change.

        Args:
            callback: Function(voice_name, rate) called on change.
        """
        self._on_ui_voice_change = callback
        # Propagate to existing UI category menu
        if "ui" in self._category_menus:
            self._category_menus["ui"].set_on_ui_voice_change(callback)

    def open(self) -> None:
        """Open the menu and load current TTS mode."""
        self.title = t("voice.title")
        settings = get_tts_settings()
        self._current_mode = settings.mode
        super().open()

    def handle_key(self, key: int, unicode: str = "") -> bool:
        """Handle keyboard input with left/right for TTS mode toggle.

        Args:
            key: pygame key code.
            unicode: Unicode character.

        Returns:
            True if key was consumed.
        """
        if not self.is_open or pygame is None:
            return False

        # Handle left/right for TTS mode toggle
        current_item = self.items[self.selected_index] if self.items else None

        if (
            current_item
            and current_item.item_id == "tts_mode"
            and key in (pygame.K_LEFT, pygame.K_RIGHT)
        ):
            self._play_click("knob")
            self._toggle_tts_mode()
            return True

        # Fall back to parent handling
        return super().handle_key(key, unicode)

    def _toggle_tts_mode(self) -> None:
        """Toggle between TTS modes."""
        if self._current_mode == TTS_MODE_REALTIME:
            self._current_mode = TTS_MODE_SELFVOICED
        else:
            self._current_mode = TTS_MODE_REALTIME

        # Save immediately
        settings = get_tts_settings()
        settings.set_mode(self._current_mode)
        settings.save()

        # Announce the new mode
        mode_display = self._get_mode_display(self._current_mode)
        self._speak(mode_display)

        # Update menu items
        self.items = self._build_items()

    def _get_mode_display(self, mode: str) -> str:
        """Get translated display name for TTS mode.

        Args:
            mode: TTS mode constant.

        Returns:
            Translated display name.
        """
        if mode == TTS_MODE_REALTIME:
            return t("voice.system_tts")
        elif mode == TTS_MODE_SELFVOICED:
            return t("voice.self_voiced")
        return mode

    def _build_items(self) -> list[MenuItem]:
        """Build menu items for each voice category."""
        items = []

        # TTS Mode toggle at the top
        mode_display = self._get_mode_display(self._current_mode)
        items.append(
            MenuItem(
                "tts_mode",
                t("voice.tts_mode_label", mode=mode_display),
            )
        )

        for category in VOICE_CATEGORIES:
            # Create or get category menu
            if category not in self._category_menus:
                self._category_menus[category] = VoiceCategoryMenu(category, self)
                # Set UI voice change callback
                if category == "ui" and self._on_ui_voice_change:
                    self._category_menus[category].set_on_ui_voice_change(self._on_ui_voice_change)

            label = t(f"voice.categories.{category}")
            items.append(
                MenuItem(
                    category,
                    label,
                    submenu=self._category_menus[category],
                )
            )

        # Add go back option
        items.append(
            MenuItem(
                "back",
                t("common.go_back"),
                action=self.close,
            )
        )

        return items

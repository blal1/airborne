"""Main menu for AirBorne flight simulator.

This is the top-level menu shown at game startup:
- Fly!
- Fly Settings (Flight Plan, Aircraft)
- Settings (Voice Settings)
- Exit

Typical usage:
    menu = MainMenu()
    menu.open()
    # In game loop:
    menu.handle_key(key, unicode)
    # Check result:
    result = menu.get_result()
"""

import logging
from collections.abc import Callable
from typing import Any

from airborne.core.i18n import t
from airborne.ui.menus.aircraft_selection import AircraftSelectionMenu
from airborne.ui.menus.base_menu import AudioMenu, MenuItem
from airborne.ui.menus.flight_plan import FlightPlanMenu
from airborne.ui.menus.voice_settings import VoiceSettingsMenu

logger = logging.getLogger(__name__)


class FlySettingsMenu(AudioMenu):
    """Fly settings submenu.

    Contains Flight Plan and Aircraft Selection.
    """

    def __init__(self, parent: AudioMenu | None = None) -> None:
        """Initialize fly settings menu."""
        super().__init__(t("menu.fly_settings.title"), parent)
        self._flight_plan_menu: FlightPlanMenu | None = None
        self._aircraft_menu: AircraftSelectionMenu | None = None

    def open(self) -> None:
        """Open the menu with updated title."""
        self.title = t("menu.fly_settings.title")
        super().open()

    def _build_items(self) -> list[MenuItem]:
        """Build menu items."""
        if not self._flight_plan_menu:
            self._flight_plan_menu = FlightPlanMenu(self)
        if not self._aircraft_menu:
            self._aircraft_menu = AircraftSelectionMenu(self)

        return [
            MenuItem(
                "flight_plan",
                t("menu.fly_settings.flight_plan"),
                submenu=self._flight_plan_menu,
            ),
            MenuItem(
                "aircraft",
                t("menu.fly_settings.aircraft_selection"),
                submenu=self._aircraft_menu,
            ),
            MenuItem(
                "back",
                t("common.go_back"),
                action=self.close,
            ),
        ]

    def get_flight_plan(self) -> dict[str, str | None]:
        """Get flight plan settings.

        Returns:
            Dictionary with departure and arrival.
        """
        if self._flight_plan_menu:
            return self._flight_plan_menu.get_result()
        return {"departure": None, "arrival": None}

    def get_aircraft(self) -> str | None:
        """Get selected aircraft.

        Returns:
            Aircraft ID or None.
        """
        if self._aircraft_menu:
            return self._aircraft_menu.get_result()
        return None


class SettingsMenu(AudioMenu):
    """Settings submenu.

    Contains Voice Settings, Language, and other configuration.
    """

    def __init__(self, parent: AudioMenu | None = None) -> None:
        """Initialize settings menu."""
        super().__init__(t("menu.settings.title"), parent)
        self._voice_settings_menu: VoiceSettingsMenu | None = None
        self._language_menu: LanguageMenu | None = None
        self._on_ui_voice_change: Callable[[str, int], None] | None = None
        self._on_language_change: Callable[[str], None] | None = None

    def set_on_ui_voice_change(self, callback: Callable[[str, int], None]) -> None:
        """Set callback for when UI voice settings change.

        Args:
            callback: Function(voice_name, rate) called on change.
        """
        self._on_ui_voice_change = callback
        # Propagate to existing voice settings menu
        if self._voice_settings_menu:
            self._voice_settings_menu.set_on_ui_voice_change(callback)
        # Propagate to existing language menu
        if self._language_menu:
            self._language_menu.set_on_ui_voice_change(callback)

    def set_on_language_change(self, callback: Callable[[str], None]) -> None:
        """Set callback for when language changes.

        Args:
            callback: Function(language_code) called on change.
        """
        self._on_language_change = callback
        # Propagate to existing language menu
        if self._language_menu:
            self._language_menu.set_on_language_change(callback)

    def open(self) -> None:
        """Open the menu with updated title."""
        self.title = t("menu.settings.title")
        super().open()

    def _build_items(self) -> list[MenuItem]:
        """Build menu items."""
        if not self._voice_settings_menu:
            self._voice_settings_menu = VoiceSettingsMenu(self)
            if self._on_ui_voice_change:
                self._voice_settings_menu.set_on_ui_voice_change(self._on_ui_voice_change)
        if not self._language_menu:
            self._language_menu = LanguageMenu(self)
            if self._on_ui_voice_change:
                self._language_menu.set_on_ui_voice_change(self._on_ui_voice_change)
            if self._on_language_change:
                self._language_menu.set_on_language_change(self._on_language_change)

        return [
            MenuItem(
                "voice_settings",
                t("menu.settings.voice_settings"),
                submenu=self._voice_settings_menu,
            ),
            MenuItem(
                "language",
                t("menu.settings.language"),
                submenu=self._language_menu,
            ),
            MenuItem(
                "back",
                t("common.go_back"),
                action=self.close,
            ),
        ]


class LanguageMenu(AudioMenu):
    """Language selection menu.

    Allows selecting the UI language.
    """

    def __init__(self, parent: AudioMenu | None = None) -> None:
        """Initialize language menu."""
        from airborne.core.i18n import SUPPORTED_LANGUAGES, get_language

        super().__init__(t("menu.settings.language"), parent)
        self._supported_languages = SUPPORTED_LANGUAGES
        self._current_language = get_language()
        self._on_ui_voice_change: Callable[[str, int], None] | None = None
        self._on_language_change: Callable[[str], None] | None = None

    def set_on_ui_voice_change(self, callback: Callable[[str, int], None]) -> None:
        """Set callback for when UI voice settings change.

        Args:
            callback: Function(voice_name, rate) called on change.
        """
        self._on_ui_voice_change = callback

    def set_on_language_change(self, callback: Callable[[str], None]) -> None:
        """Set callback for when language changes.

        Args:
            callback: Function(language_code) called on change.
        """
        self._on_language_change = callback

    def open(self) -> None:
        """Open the menu with updated title and current language."""
        from airborne.core.i18n import get_language

        self.title = t("menu.settings.language")
        self._current_language = get_language()
        super().open()

    def _build_items(self) -> list[MenuItem]:
        """Build menu items for each language."""
        from functools import partial

        items = []

        for lang_code, lang_name in self._supported_languages.items():
            # Show checkmark for current language
            label = f"{lang_name} *" if lang_code == self._current_language else lang_name
            items.append(
                MenuItem(
                    lang_code,
                    label,
                    action=partial(self._select_language, lang_code),
                )
            )

        items.append(
            MenuItem(
                "back",
                t("common.go_back"),
                action=self.close,
            )
        )

        return items

    def _select_language(self, lang_code: str) -> None:
        """Select a language and save to settings.

        Args:
            lang_code: Language code to select.
        """
        from airborne.core.i18n import set_language
        from airborne.settings import get_tts_settings

        if lang_code == self._current_language:
            self._speak(t("common.selected"))
            return

        # Update i18n system
        set_language(lang_code)
        self._current_language = lang_code

        # Save to settings and reset voices to language defaults
        settings = get_tts_settings()
        settings.set_language(lang_code, reset_voices=True)
        settings.save()

        # Notify about UI voice change so TTS uses the new language voice
        if self._on_ui_voice_change:
            ui_voice = settings.get_voice("ui")
            self._on_ui_voice_change(ui_voice.voice_name, ui_voice.rate)

        # Notify about language change to trigger voice cache refresh
        if self._on_language_change:
            self._on_language_change(lang_code)

        # Announce in new language
        self._speak(t("common.saved"))

        # Rebuild menu items to update checkmarks
        self.items = self._build_items()

        # Propagate translation reload to parent menus
        self.reload_translations()


class MainMenu(AudioMenu):
    """Main menu for AirBorne.

    Top-level menu shown at game startup.
    """

    # Menu result codes
    RESULT_NONE = None
    RESULT_FLY = "fly"
    RESULT_EXIT = "exit"

    def __init__(self) -> None:
        """Initialize main menu."""
        super().__init__(t("menu.main.title"))
        self._fly_settings_menu: FlySettingsMenu | None = None
        self._settings_menu: SettingsMenu | None = None
        self._result: str | None = None

        # Callbacks for menu actions
        self._on_fly: Callable[[], None] | None = None
        self._on_exit: Callable[[], None] | None = None

        # UI voice change callback
        self._on_ui_voice_change: Callable[[str, int], None] | None = None
        self._on_language_change: Callable[[str], None] | None = None

    def set_on_ui_voice_change(self, callback: Callable[[str, int], None]) -> None:
        """Set callback for when UI voice settings change.

        Args:
            callback: Function(voice_name, rate) called on change.
        """
        self._on_ui_voice_change = callback
        # Propagate to existing settings menu
        if self._settings_menu:
            self._settings_menu.set_on_ui_voice_change(callback)

    def set_on_language_change(self, callback: Callable[[str], None]) -> None:
        """Set callback for when language changes.

        Args:
            callback: Function(language_code) called on change.
        """
        self._on_language_change = callback
        # Propagate to existing settings menu
        if self._settings_menu:
            self._settings_menu.set_on_language_change(callback)

    def set_callbacks(
        self,
        on_fly: Callable[[], None] | None = None,
        on_exit: Callable[[], None] | None = None,
    ) -> None:
        """Set action callbacks.

        Args:
            on_fly: Called when Fly! is selected.
            on_exit: Called when Exit is selected.
        """
        self._on_fly = on_fly
        self._on_exit = on_exit

    def open(self, is_startup: bool = False) -> None:
        """Open the menu with welcome announcement on startup.

        Args:
            is_startup: If True, announce "AirBorne" first (initial launch).
        """
        self.title = t("menu.main.title")

        if is_startup:
            # Startup sequence: "AirBorne" -> menu title -> first item
            self.items = self._build_items()
            self.selected_index = 0
            self.is_open = True
            self._active_child = None

            # Build announcement: "AirBorne. Main Menu. 4 items. Fly!"
            welcome = t("menu.main.welcome")
            item_count = f"{len(self.items)} items."
            first_item = self.items[0].label if self.items else ""
            announcement = f"{welcome}. {self.title}. {item_count} {first_item}"
            self._speak(announcement)
        else:
            # Normal submenu return - standard behavior
            super().open()

    def _build_items(self) -> list[MenuItem]:
        """Build main menu items."""
        if not self._fly_settings_menu:
            self._fly_settings_menu = FlySettingsMenu(self)
        if not self._settings_menu:
            self._settings_menu = SettingsMenu(self)
            if self._on_ui_voice_change:
                self._settings_menu.set_on_ui_voice_change(self._on_ui_voice_change)
            if self._on_language_change:
                self._settings_menu.set_on_language_change(self._on_language_change)

        return [
            MenuItem(
                "fly",
                t("menu.main.fly"),
                action=self._start_flight,
            ),
            MenuItem(
                "fly_settings",
                t("menu.main.fly_settings"),
                submenu=self._fly_settings_menu,
            ),
            MenuItem(
                "settings",
                t("menu.main.settings"),
                submenu=self._settings_menu,
            ),
            MenuItem(
                "exit",
                t("menu.main.exit"),
                action=self._exit_game,
            ),
        ]

    def _start_flight(self) -> None:
        """Start the flight.

        Note: Does not close menu - the menu runner handles closing after
        the music fadeout completes.
        """
        self._result = self.RESULT_FLY
        self._speak(t("menu.main.starting_flight"))

        if self._on_fly:
            self._on_fly()

    def _exit_game(self) -> None:
        """Exit the game."""
        self._result = self.RESULT_EXIT
        self._speak(t("menu.main.goodbye"))

        if self._on_exit:
            self._on_exit()

        self.close()

    def get_result(self) -> str | None:
        """Get menu result.

        Returns:
            "fly", "exit", or None.
        """
        return self._result

    def get_flight_config(self) -> dict[str, Any]:
        """Get full flight configuration from menu selections.

        Returns:
            Dictionary with all flight settings.
        """
        config: dict[str, Any] = {
            "departure": None,
            "arrival": None,
            "aircraft": None,
        }

        if self._fly_settings_menu:
            flight_plan = self._fly_settings_menu.get_flight_plan()
            config["departure"] = flight_plan.get("departure")
            config["arrival"] = flight_plan.get("arrival")
            config["aircraft"] = self._fly_settings_menu.get_aircraft()

        return config

"""Flight plan menu for departure/arrival airport selection.

This menu allows setting up a flight plan:
- Departure airport (with autocomplete)
- Arrival airport (with autocomplete)
- Future: waypoints

Typical usage:
    menu = FlightPlanMenu()
    menu.open()
    # After closing:
    result = menu.get_result()
    # result = {"departure": "LFPG", "arrival": "KJFK"}
"""

import logging
from typing import Any

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

from airborne.airports.airport_index import AirportInfo, get_airport_index
from airborne.core.i18n import t
from airborne.ui.menus.base_menu import AudioMenu, MenuItem
from airborne.ui.widgets.text_input import TextInputWidget

logger = logging.getLogger(__name__)


class AirportInputMenu(AudioMenu):
    """Menu for selecting an airport with autocomplete.

    This is a special menu that wraps an autocomplete widget.
    """

    def __init__(
        self,
        title: str,
        field_name: str,
        parent: AudioMenu | None = None,
    ) -> None:
        """Initialize airport input menu.

        Args:
            title: Menu title (e.g., "Departure Airport").
            field_name: Field name for results (e.g., "departure").
            parent: Parent menu.
        """
        super().__init__(title, parent)
        self.field_name = field_name
        self._selected_airport: AirportInfo | None = None
        self._widget: TextInputWidget | None = None

    def open(self) -> None:
        """Open the menu."""
        self.is_open = True

        # Create text input widget with autocomplete
        self._widget = TextInputWidget(
            widget_id=f"airport_{self.field_name}",
            label=self.title,
            search_func=self._search_airports,
            min_query_length=2,
            max_suggestions=8,
            uppercase=True,
            on_submit=self._on_airport_selected,
        )
        self._widget.set_audio_callbacks(
            speak=self._speak_callback,
            click=lambda path: self._play_sound_callback(path, 0.7)
            if self._play_sound_callback
            else None,
        )
        self._widget.activate()

        self._speak(f"{self.title}. {t('flight_plan.type_icao')}")

    def _search_airports(self, query: str) -> list[tuple[str, str]]:
        """Search airports for autocomplete.

        Args:
            query: Search query string.

        Returns:
            List of (icao, display) tuples.
        """
        try:
            index = get_airport_index()
            results = index.search(query, limit=8)
            return [(a.icao, a.display_name()) for a in results]
        except Exception as e:
            logger.error("Airport search failed: %s", e)
            return []

    def _on_airport_selected(self, event: Any) -> None:
        """Handle airport selection.

        Args:
            event: Widget event with selected value.
        """
        icao = event.value
        if icao:
            try:
                index = get_airport_index()
                self._selected_airport = index.get(icao)
                if self._selected_airport:
                    self._speak(f"Selected: {self._selected_airport.display_name()}")
                else:
                    self._speak(f"Selected: {icao}")
            except Exception:
                self._speak(f"Selected: {icao}")

        self.close()

    def handle_key(self, key: int, unicode: str = "") -> bool:
        """Handle keyboard input.

        Args:
            key: pygame key code.
            unicode: Unicode character.

        Returns:
            True if key was consumed.
        """
        if not self.is_open:
            return False

        if pygame is None:
            return False

        # Escape - go back without selecting
        if key == pygame.K_ESCAPE:
            self._play_click("switch")
            self._speak(t("common.cancelled"))
            self.close()
            return True

        # Delegate to widget
        if self._widget:
            return self._widget.handle_key(key, unicode)

        return False

    def _build_items(self) -> list[MenuItem]:
        """Build menu items (not used - this menu uses a widget instead).

        Returns:
            Empty list since this menu doesn't use traditional items.
        """
        return []

    def get_result(self) -> str | None:
        """Get selected airport ICAO code.

        Returns:
            ICAO code or None if not selected.
        """
        if self._selected_airport:
            return self._selected_airport.icao
        return self._widget.get_value() if self._widget else None


class FlightPlanMenu(AudioMenu):
    """Flight plan configuration menu.

    Allows setting departure and arrival airports.
    """

    def __init__(self, parent: AudioMenu | None = None) -> None:
        """Initialize flight plan menu."""
        super().__init__(t("flight_plan.title"), parent)
        self._departure: str | None = None
        self._arrival: str | None = None
        self._departure_menu: AirportInputMenu | None = None
        self._arrival_menu: AirportInputMenu | None = None

    def open(self) -> None:
        """Open the menu with updated title."""
        self.title = t("flight_plan.title")
        super().open()

    def _build_items(self) -> list[MenuItem]:
        """Build menu items."""
        # Get airport display names
        dep_display = self._get_airport_display(self._departure)
        arr_display = self._get_airport_display(self._arrival)

        # Create submenus
        if not self._departure_menu:
            self._departure_menu = AirportInputMenu(
                t("flight_plan.departure_airport"), "departure", self
            )
        if not self._arrival_menu:
            self._arrival_menu = AirportInputMenu(t("flight_plan.arrival_airport"), "arrival", self)

        return [
            MenuItem(
                "departure",
                f"{t('flight_plan.departure')}: {dep_display}",
                action=self._edit_departure,
            ),
            MenuItem(
                "arrival",
                f"{t('flight_plan.arrival')}: {arr_display}",
                action=self._edit_arrival,
            ),
            MenuItem(
                "clear",
                t("flight_plan.clear"),
                action=self._clear_plan,
            ),
            MenuItem(
                "confirm",
                t("flight_plan.confirm_and_back"),
                action=self._confirm_and_close,
            ),
        ]

    def _get_airport_display(self, icao: str | None) -> str:
        """Get display name for an airport.

        Args:
            icao: ICAO code or None.

        Returns:
            Display string.
        """
        if not icao:
            return t("common.not_set")

        try:
            index = get_airport_index()
            airport = index.get(icao)
            if airport:
                return airport.short_name()
        except Exception:
            pass

        return icao

    def _edit_departure(self) -> None:
        """Open departure airport selection."""
        if self._departure_menu:
            self._departure_menu.set_audio_callbacks(
                speak=self._speak_callback,
                play_sound=self._play_sound_callback,
                tts_client=self._tts_client,
            )
            self._departure_menu.open()
            self._active_child = self._departure_menu

    def _edit_arrival(self) -> None:
        """Open arrival airport selection."""
        if self._arrival_menu:
            self._arrival_menu.set_audio_callbacks(
                speak=self._speak_callback,
                play_sound=self._play_sound_callback,
                tts_client=self._tts_client,
            )
            self._arrival_menu.open()
            self._active_child = self._arrival_menu

    def _clear_plan(self) -> None:
        """Clear the flight plan."""
        self._departure = None
        self._arrival = None
        self.items = self._build_items()
        self._speak(t("flight_plan.plan_cleared"))

    def _confirm_and_close(self) -> None:
        """Confirm and close the menu."""
        # Get results from submenus
        if self._departure_menu:
            result = self._departure_menu.get_result()
            if result:
                self._departure = result

        if self._arrival_menu:
            result = self._arrival_menu.get_result()
            if result:
                self._arrival = result

        if self._departure and self._arrival:
            self._speak(t("flight_plan.plan_set", departure=self._departure, arrival=self._arrival))
        elif self._departure:
            self._speak(f"{t('flight_plan.departure')}: {self._departure}")
        elif self._arrival:
            self._speak(f"{t('flight_plan.arrival')}: {self._arrival}")
        else:
            self._speak(t("flight_plan.no_plan"))

        self.close()

    def handle_key(self, key: int, unicode: str = "") -> bool:
        """Handle keyboard input."""
        # Update results when child closes
        if self._active_child and not self._active_child.is_open:
            # Capture result from child
            if isinstance(self._active_child, AirportInputMenu):
                result = self._active_child.get_result()
                if result:
                    if self._active_child.field_name == "departure":
                        self._departure = result
                    elif self._active_child.field_name == "arrival":
                        self._arrival = result
                    # Rebuild items to show updated values
                    self.items = self._build_items()

            self._active_child = None
            self._announce_current_item()
            return True

        return super().handle_key(key, unicode)

    def get_result(self) -> dict[str, str | None]:
        """Get flight plan result.

        Returns:
            Dictionary with "departure" and "arrival" keys.
        """
        return {
            "departure": self._departure,
            "arrival": self._arrival,
        }

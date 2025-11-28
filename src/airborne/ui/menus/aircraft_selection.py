"""Aircraft selection menu.

This menu allows selecting an aircraft from available configurations
in config/aircraft/*.yaml.

Typical usage:
    menu = AircraftSelectionMenu()
    menu.open()
    # After closing:
    result = menu.get_result()
    # result = "cessna172"
"""

import logging
from functools import partial
from typing import Any

import yaml

from airborne.core.i18n import t
from airborne.core.resource_path import get_resource_path
from airborne.ui.menus.base_menu import AudioMenu, MenuItem

logger = logging.getLogger(__name__)


class AircraftSelectionMenu(AudioMenu):
    """Aircraft selection menu.

    Lists available aircraft configurations from config/aircraft.
    """

    def __init__(self, parent: AudioMenu | None = None) -> None:
        """Initialize aircraft selection menu."""
        super().__init__(t("aircraft.title"), parent)
        self._selected_aircraft: str | None = None
        self._aircraft_list: list[dict[str, Any]] = []

    def open(self) -> None:
        """Open the menu and load aircraft list."""
        self.title = t("aircraft.title")
        self._load_aircraft_list()
        super().open()

    def _load_aircraft_list(self) -> None:
        """Load available aircraft from config/aircraft directory."""
        self._aircraft_list = []

        try:
            aircraft_dir = get_resource_path("config/aircraft")
            if not aircraft_dir.exists():
                logger.warning("Aircraft config directory not found: %s", aircraft_dir)
                return

            for yaml_file in sorted(aircraft_dir.glob("*.yaml")):
                try:
                    with open(yaml_file, encoding="utf-8") as f:
                        config = yaml.safe_load(f)

                    if config:
                        aircraft_id = yaml_file.stem
                        name = config.get("name", aircraft_id)
                        description = config.get("description", "")

                        self._aircraft_list.append(
                            {
                                "id": aircraft_id,
                                "name": name,
                                "description": description,
                                "path": str(yaml_file),
                            }
                        )
                except Exception as e:
                    logger.warning("Failed to load aircraft config %s: %s", yaml_file, e)

            logger.info("Loaded %d aircraft configurations", len(self._aircraft_list))

        except Exception as e:
            logger.error("Failed to scan aircraft directory: %s", e)

    def _build_items(self) -> list[MenuItem]:
        """Build menu items from aircraft list."""
        items = []

        for aircraft in self._aircraft_list:
            label = aircraft["name"]
            if aircraft["description"]:
                label = f"{aircraft['name']} - {aircraft['description']}"

            items.append(
                MenuItem(
                    aircraft["id"],
                    label,
                    action=partial(self._select_aircraft, aircraft["id"]),
                    data=aircraft,
                )
            )

        if not items:
            items.append(
                MenuItem(
                    "none",
                    t("aircraft.no_aircraft"),
                    enabled=False,
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

    def _select_aircraft(self, aircraft_id: str) -> None:
        """Select an aircraft.

        Args:
            aircraft_id: Aircraft ID to select.
        """
        self._selected_aircraft = aircraft_id

        # Find aircraft info
        for aircraft in self._aircraft_list:
            if aircraft["id"] == aircraft_id:
                self._speak(f"Selected: {aircraft['name']}")
                break

        self.close()

    def get_result(self) -> str | None:
        """Get selected aircraft ID.

        Returns:
            Aircraft ID or None if not selected.
        """
        return self._selected_aircraft

"""Main menu system for AirBorne flight simulator.

This package provides the audio-accessible main menu system:
- MainMenu: Top-level menu with Fly!, Settings, etc.
- VoiceSettingsMenu: TTS voice configuration per category
- FlightPlanMenu: Departure/arrival airport selection
- AircraftSelectionMenu: Aircraft model selection
- MenuRunner: Standalone menu runner for game startup
"""

from airborne.ui.menus.aircraft_selection import AircraftSelectionMenu
from airborne.ui.menus.base_menu import AudioMenu, MenuItem
from airborne.ui.menus.flight_plan import FlightPlanMenu
from airborne.ui.menus.main_menu import MainMenu
from airborne.ui.menus.menu_runner import MenuRunner
from airborne.ui.menus.voice_settings import VoiceSettingsMenu

__all__ = [
    "AudioMenu",
    "MenuItem",
    "MainMenu",
    "VoiceSettingsMenu",
    "FlightPlanMenu",
    "AircraftSelectionMenu",
    "MenuRunner",
]

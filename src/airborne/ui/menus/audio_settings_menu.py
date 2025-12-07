"""Audio settings menu for input device and volume configuration.

This menu allows configuring:
- Audio input device (microphone) selection
- Volume levels for each audio category (master, music, engine, etc.)

Navigation:
- Up/Down: Navigate between settings
- Left/Right: Adjust volume (5% steps) or cycle devices
- Enter: Confirm selection
- Escape: Go back

Typical usage:
    menu = AudioSettingsMenu()
    menu.set_audio_facade(audio_facade)  # For real-time volume updates
    menu.open()
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

from airborne.core.i18n import t
from airborne.settings.audio_settings import VOLUME_CATEGORIES, get_audio_settings
from airborne.ui.menus.base_menu import AudioMenu, MenuItem

if TYPE_CHECKING:
    from airborne.audio.audio_facade import AudioFacade

logger = logging.getLogger(__name__)

# Volume step size (5%)
VOLUME_STEP = 0.05


class AudioSettingsMenu(AudioMenu):
    """Audio settings menu.

    Provides UI for selecting audio input device and adjusting volume levels.
    Uses left/right to cycle devices and adjust volumes.
    """

    def __init__(self, parent: AudioMenu | None = None) -> None:
        """Initialize audio settings menu.

        Args:
            parent: Parent menu.
        """
        super().__init__(t("audio.title"), parent)
        self._devices: list[tuple[int, str]] = []  # (index, name)
        self._current_device_index = 0
        self._volume_menu: VolumeSettingsMenu | None = None
        # Audio facade for real-time volume updates
        self._audio_facade: "AudioFacade | None" = None
        # FMOD system for device enumeration
        self._fmod_system: Any = None

    def set_audio_facade(self, facade: "AudioFacade | None") -> None:
        """Set the audio facade for real-time volume updates.

        Args:
            facade: AudioFacade instance.
        """
        self._audio_facade = facade
        if self._volume_menu:
            self._volume_menu.set_audio_facade(facade)

    def set_fmod_system(self, system: Any) -> None:
        """Set the FMOD system for device enumeration.

        Args:
            system: FMOD System instance.
        """
        self._fmod_system = system

    def open(self) -> None:
        """Open the menu and load devices."""
        self.title = t("audio.title")
        self._load_devices()

        # Load current device selection
        settings = get_audio_settings()
        self._current_device_index = 0
        for i, (idx, _) in enumerate(self._devices):
            if idx == settings.input_device_index:
                self._current_device_index = i
                break

        super().open()

    def _load_devices(self) -> None:
        """Load available recording devices from FMOD."""
        self._devices = []

        try:
            from airborne.audio.recording.audio_recorder import AudioRecorder, FMOD_AVAILABLE

            if not FMOD_AVAILABLE:
                logger.warning("FMOD not available for device enumeration")
                self._devices = [(0, t("audio.default_device"))]
                return

            # Use the FMOD system if provided
            if self._fmod_system:
                try:
                    recorder = AudioRecorder(self._fmod_system)
                    devices = recorder.get_recording_devices()
                    for dev in devices:
                        self._devices.append((dev.index, dev.name))
                    logger.info("Found %d recording devices", len(self._devices))
                except Exception as e:
                    logger.warning("Could not enumerate recording devices: %s", e)

        except Exception as e:
            logger.error("Failed to load recording devices: %s", e)

        # Fallback if no devices found
        if not self._devices:
            self._devices = [(0, t("audio.default_device"))]

    def _build_items(self) -> list[MenuItem]:
        """Build menu items."""
        items = []

        # Input device selection
        current_device_name = (
            self._devices[self._current_device_index][1]
            if self._devices
            else t("audio.default_device")
        )
        items.append(
            MenuItem(
                "input_device",
                t("audio.input_device", device=current_device_name),
            )
        )

        # Volume settings submenu
        if not self._volume_menu:
            self._volume_menu = VolumeSettingsMenu(self)
            if self._audio_facade:
                self._volume_menu.set_audio_facade(self._audio_facade)

        items.append(
            MenuItem(
                "volumes",
                t("audio.volume_settings"),
                submenu=self._volume_menu,
            )
        )

        # Save and go back
        items.append(
            MenuItem(
                "save",
                t("audio.save_and_back"),
                action=self._save_and_close,
            )
        )

        return items

    def handle_key(self, key: int, unicode: str = "") -> bool:
        """Handle keyboard input with left/right for device cycling.

        Args:
            key: pygame key code.
            unicode: Unicode character.

        Returns:
            True if key was consumed.
        """
        if not self.is_open or pygame is None:
            return False

        # Handle left/right for input device
        current_item = self.items[self.selected_index] if self.items else None

        if current_item and current_item.item_id == "input_device":
            if key == pygame.K_LEFT:
                self._play_click("knob")
                self._cycle_device(-1)
                return True
            elif key == pygame.K_RIGHT:
                self._play_click("knob")
                self._cycle_device(1)
                return True

        return super().handle_key(key, unicode)

    def _cycle_device(self, direction: int) -> None:
        """Cycle through available input devices.

        Args:
            direction: 1 for next, -1 for previous.
        """
        if not self._devices:
            self._speak(t("common.none_available"))
            return

        self._current_device_index = (self._current_device_index + direction) % len(
            self._devices
        )
        device_idx, device_name = self._devices[self._current_device_index]

        # Update settings
        settings = get_audio_settings()
        settings.set_input_device(device_idx, device_name)

        # Announce device name
        self._speak(device_name)

        # Update menu display
        self.items = self._build_items()

    def _save_and_close(self) -> None:
        """Save settings and close menu."""
        settings = get_audio_settings()
        settings.save()
        self._speak(t("common.saved"))
        self.close()


class VolumeSettingsMenu(AudioMenu):
    """Volume settings submenu.

    Allows adjusting volume levels for each audio category.
    """

    def __init__(self, parent: AudioMenu | None = None) -> None:
        """Initialize volume settings menu.

        Args:
            parent: Parent menu.
        """
        super().__init__(t("audio.volume_settings"), parent)
        self._audio_facade: "AudioFacade | None" = None

    def set_audio_facade(self, facade: "AudioFacade | None") -> None:
        """Set the audio facade for real-time volume updates.

        Args:
            facade: AudioFacade instance.
        """
        self._audio_facade = facade

    def open(self) -> None:
        """Open the menu."""
        self.title = t("audio.volume_settings")
        super().open()

    def _build_items(self) -> list[MenuItem]:
        """Build menu items for each volume category."""
        items = []
        settings = get_audio_settings()

        for category in VOLUME_CATEGORIES:
            volume = settings.get_volume(category)
            percent = int(volume * 100)
            label = t(f"audio.volume.{category}", percent=percent)

            items.append(
                MenuItem(
                    f"vol_{category}",
                    label,
                )
            )

        # Go back
        items.append(
            MenuItem(
                "back",
                t("common.go_back"),
                action=self.close,
            )
        )

        return items

    def handle_key(self, key: int, unicode: str = "") -> bool:
        """Handle keyboard input with left/right for volume adjustment.

        Args:
            key: pygame key code.
            unicode: Unicode character.

        Returns:
            True if key was consumed.
        """
        if not self.is_open or pygame is None:
            return False

        current_item = self.items[self.selected_index] if self.items else None

        # Handle left/right for volume items
        if current_item and current_item.item_id.startswith("vol_"):
            category = current_item.item_id[4:]  # Remove "vol_" prefix

            if key == pygame.K_LEFT:
                self._play_click("knob")
                self._adjust_volume(category, -VOLUME_STEP)
                return True
            elif key == pygame.K_RIGHT:
                self._play_click("knob")
                self._adjust_volume(category, VOLUME_STEP)
                return True

        return super().handle_key(key, unicode)

    def _adjust_volume(self, category: str, delta: float) -> None:
        """Adjust volume for a category.

        Args:
            category: Volume category name.
            delta: Volume change (positive or negative).
        """
        settings = get_audio_settings()
        current = settings.get_volume(category)
        new_volume = max(0.0, min(1.0, current + delta))

        # Round to nearest step to avoid floating point drift
        new_volume = round(new_volume / VOLUME_STEP) * VOLUME_STEP
        new_volume = max(0.0, min(1.0, new_volume))

        settings.set_volume(category, new_volume)

        # Apply changes in real-time to the audio facade
        if self._audio_facade:
            if category == "master":
                self._audio_facade.volumes.set_master_volume(new_volume)
            else:
                self._audio_facade.volumes.set_category_volume(category, new_volume)

        # Announce new value
        percent = int(new_volume * 100)
        self._speak(f"{percent}%")

        # Update menu display
        self.items = self._build_items()

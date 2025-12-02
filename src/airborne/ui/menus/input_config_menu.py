"""Input configuration menu for keybinding customization.

This menu allows users to view and edit keybindings for all actions,
organized by panel/context. Users can:
- Navigate with Up/Down arrows
- Press Space to edit a binding
- Press Delete to unbind an action
- Access panel assignments and reset options

Typical usage:
    menu = InputConfigMenu(aircraft_id="cessna172", parent=fly_settings_menu)
    menu.open()
"""

import logging
from functools import partial
from pathlib import Path
from typing import Any

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

import yaml

from airborne.core.i18n import t
from airborne.settings.keybindings_settings import (
    KeybindingsSettings,
    get_keybindings_settings,
)
from airborne.ui.menus.base_menu import AudioMenu, MenuItem

logger = logging.getLogger(__name__)

# Context display order
CONTEXT_ORDER = [
    "global",
    "flight_mode",
    "radio_panel",
    "atc_menu",
    "checklist_menu",
    "ground_services_menu",
]


class InputConfigMenu(AudioMenu):
    """Main input configuration menu.

    Shows all bindings grouped by context/panel with edit capability.

    Attributes:
        aircraft_id: Aircraft identifier for saving settings.
        settings: Keybindings settings for this aircraft.
        default_bindings: Default bindings loaded from YAML.
    """

    def __init__(
        self,
        aircraft_id: str,
        config_dir: Path | None = None,
        parent: AudioMenu | None = None,
    ) -> None:
        """Initialize input configuration menu.

        Args:
            aircraft_id: Aircraft identifier.
            config_dir: Path to config directory (for loading defaults).
            parent: Parent menu.
        """
        super().__init__(t("input_config.title"), parent)
        self.aircraft_id = aircraft_id
        self.config_dir = config_dir or Path("config/input")
        self.settings = get_keybindings_settings(aircraft_id)
        self.default_bindings: dict[str, list[dict[str, Any]]] = {}
        self._pending_changes = False

        # Submenus (created lazily)
        self._context_menus: dict[str, ContextBindingsMenu] = {}
        self._panel_assignment_menu: PanelAssignmentMenu | None = None
        self._reset_menu: ResetOptionsMenu | None = None

        self._load_default_bindings()

    def _load_default_bindings(self) -> None:
        """Load default bindings from YAML context files."""
        context_dir = self.config_dir / "contexts"
        if not context_dir.exists():
            logger.warning("Context directory not found: %s", context_dir)
            return

        for yaml_file in context_dir.glob("*.yaml"):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    config = yaml.safe_load(f)

                context_name = config.get("context", "")
                bindings = config.get("bindings", [])
                self.default_bindings[context_name] = bindings
                logger.debug("Loaded %d default bindings for %s", len(bindings), context_name)

            except Exception as e:
                logger.error("Failed to load %s: %s", yaml_file, e)

    def open(self) -> None:
        """Open the menu and announce title."""
        self.title = t("input_config.title")
        super().open()
        self._speak(t("input_config.menu_opened"))

    def _build_items(self) -> list[MenuItem]:
        """Build menu items - one per context/panel."""
        items = []

        # Add context submenus in order
        for context_name in CONTEXT_ORDER:
            if context_name in self.default_bindings:
                context_label = t(f"input_config.contexts.{context_name}")
                binding_count = len(self.default_bindings[context_name])

                # Create submenu if not exists
                if context_name not in self._context_menus:
                    self._context_menus[context_name] = ContextBindingsMenu(
                        context_name=context_name,
                        default_bindings=self.default_bindings[context_name],
                        settings=self.settings,
                        parent=self,
                    )

                items.append(
                    MenuItem(
                        context_name,
                        f"{context_label} ({binding_count})",
                        submenu=self._context_menus[context_name],
                    )
                )

        # Add panel assignments
        if not self._panel_assignment_menu:
            self._panel_assignment_menu = PanelAssignmentMenu(settings=self.settings, parent=self)
        items.append(
            MenuItem(
                "panel_assignments",
                t("input_config.panel_assignments"),
                submenu=self._panel_assignment_menu,
            )
        )

        # Add reset options
        if not self._reset_menu:
            self._reset_menu = ResetOptionsMenu(
                settings=self.settings,
                contexts=list(self.default_bindings.keys()),
                parent=self,
            )
        items.append(
            MenuItem(
                "reset",
                t("input_config.reset_options"),
                submenu=self._reset_menu,
            )
        )

        # Add save and back
        items.append(
            MenuItem(
                "save_back",
                t("input_config.save_and_back"),
                action=self._save_and_close,
            )
        )

        return items

    def _save_and_close(self) -> None:
        """Save settings and close menu."""
        # Check for conflicts before saving
        conflicts = self.settings.detect_conflicts(self.default_bindings)
        if conflicts:
            conflict_desc = conflicts[0]
            action1 = t(f"input_config.actions.{conflict_desc['actions'][0]}")
            action2 = t(f"input_config.actions.{conflict_desc['actions'][1]}")
            self._speak(
                f"{t('input_config.conflict_detected')}. "
                f"{action1} {t('input_config.conflict_with')} {action2}. "
                f"{t('input_config.resolve_conflict')}"
            )
            return

        if self.settings.is_dirty:
            self.settings.save()
            self._speak(t("common.saved"))
        else:
            self._speak(t("common.back"))

        self.close()

    def close(self) -> None:
        """Close menu with announcement."""
        self._speak(t("input_config.menu_closed"))
        super().close()


class ContextBindingsMenu(AudioMenu):
    """Menu showing all bindings for a single context.

    Displays each action with its current binding, allowing edit via Space.
    """

    def __init__(
        self,
        context_name: str,
        default_bindings: list[dict[str, Any]],
        settings: KeybindingsSettings,
        parent: AudioMenu | None = None,
    ) -> None:
        """Initialize context bindings menu.

        Args:
            context_name: Context name (e.g., "flight_mode").
            default_bindings: Default bindings from YAML.
            settings: User keybindings settings.
            parent: Parent menu.
        """
        context_label = t(f"input_config.contexts.{context_name}")
        super().__init__(context_label, parent)
        self.context_name = context_name
        self.default_bindings = default_bindings
        self.settings = settings

        # Edit mode state
        self._edit_mode = False
        self._editing_action: str | None = None
        self._captured_keys: list[str] = []
        self._captured_modifiers: list[str] = []

    def _build_items(self) -> list[MenuItem]:
        """Build menu items for each action in context."""
        items = []

        for binding in self.default_bindings:
            action = binding.get("action", "")
            if not action:
                continue

            # Get current binding (override or default)
            override = self.settings.get_override(self.context_name, action)
            if override:
                if override.unbound:
                    key_str = t("input_config.unbound")
                else:
                    key_str = self._format_binding(override.keys, override.modifiers)
            else:
                keys = binding.get("keys") or [binding.get("key")]
                if keys and keys[0]:
                    keys = [str(k) for k in keys if k]
                else:
                    keys = []
                modifiers = binding.get("modifiers", [])
                key_str = self._format_binding(keys, modifiers)

            # Get translated action name
            action_label = t(f"input_config.actions.{action}")
            label = f"{action_label}: {key_str}"

            items.append(
                MenuItem(
                    action,
                    label,
                    action=partial(self._start_edit, action),
                    data={"default_binding": binding},
                )
            )

        # Add back option
        items.append(
            MenuItem(
                "back",
                t("common.go_back"),
                action=self.close,
            )
        )

        return items

    def _format_binding(self, keys: list[str], modifiers: list[str]) -> str:
        """Format binding for display.

        Args:
            keys: List of key names.
            modifiers: List of modifier names.

        Returns:
            Formatted string like "Shift plus A".
        """
        if not keys:
            return t("input_config.no_binding")

        parts = []

        # Add modifiers
        for mod in modifiers:
            mod_name = t(f"input_config.modifiers.{mod.lower()}")
            parts.append(mod_name)

        # Add key(s)
        for key in keys:
            key_name = t(f"input_config.keys.{key.lower()}")
            parts.append(key_name)

        plus = t("input_config.plus")
        return f" {plus} ".join(parts)

    def handle_key(self, key: int, unicode: str = "") -> bool:
        """Handle keyboard input, including edit mode.

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

        # If in edit mode, capture the key
        if self._edit_mode:
            return self._handle_edit_key(key)

        # Space to start editing current item
        if key == pygame.K_SPACE:
            item = self.items[self.selected_index]
            if item.item_id != "back":
                self._start_edit(item.item_id)
                return True

        # Delete to unbind current item
        if key in (pygame.K_DELETE, pygame.K_BACKSPACE):
            item = self.items[self.selected_index]
            if item.item_id != "back":
                self._unbind_action(item.item_id)
                return True

        # Default handling
        return super().handle_key(key, unicode)

    def _start_edit(self, action: str) -> None:
        """Start editing a binding.

        Args:
            action: Action to edit.
        """
        self._edit_mode = True
        self._editing_action = action
        self._captured_keys = []
        self._captured_modifiers = []

        action_label = t(f"input_config.actions.{action}")
        self._speak(
            f"{action_label}. {t('input_config.press_key_combo')}. "
            f"{t('input_config.confirm_binding')}"
        )

    def _handle_edit_key(self, key: int) -> bool:
        """Handle key press in edit mode.

        Args:
            key: pygame key code.

        Returns:
            True (always consumes in edit mode).
        """
        if pygame is None:
            return True

        # Escape cancels
        if key == pygame.K_ESCAPE:
            self._edit_mode = False
            self._editing_action = None
            self._speak(t("input_config.binding_cancelled"))
            return True

        # Enter confirms
        if key == pygame.K_RETURN:
            if self._captured_keys:
                self._save_binding()
            else:
                self._speak(t("input_config.press_key"))
            return True

        # Delete unbinds
        if key == pygame.K_DELETE:
            self._unbind_action(self._editing_action)
            self._edit_mode = False
            self._editing_action = None
            return True

        # Get key name and modifiers
        key_name = pygame.key.name(key).upper()
        mods = pygame.key.get_mods()

        # Skip pure modifier keys
        if key_name in (
            "LEFT SHIFT",
            "RIGHT SHIFT",
            "LEFT CTRL",
            "RIGHT CTRL",
            "LEFT ALT",
            "RIGHT ALT",
            "LEFT META",
            "RIGHT META",
        ):
            return True

        # Capture modifiers
        self._captured_modifiers = []
        if mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT):
            self._captured_modifiers.append("SHIFT")
        if mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL):
            self._captured_modifiers.append("CTRL")
        if mods & (pygame.KMOD_ALT | pygame.KMOD_LALT | pygame.KMOD_RALT):
            self._captured_modifiers.append("ALT")

        # Capture key
        self._captured_keys = [key_name]

        # Announce the captured combination
        binding_str = self._format_binding(self._captured_keys, self._captured_modifiers)
        self._speak(f"{binding_str}. {t('input_config.confirm_binding')}")

        return True

    def _save_binding(self) -> None:
        """Save the captured binding."""
        if not self._editing_action or not self._captured_keys:
            return

        self.settings.set_binding(
            self.context_name,
            self._editing_action,
            self._captured_keys,
            self._captured_modifiers,
        )

        self._speak(t("input_config.binding_saved"))

        # Rebuild menu to show updated binding
        self.items = self._build_items()

        # Exit edit mode
        self._edit_mode = False
        self._editing_action = None
        self._captured_keys = []
        self._captured_modifiers = []

    def _unbind_action(self, action: str | None) -> None:
        """Unbind an action.

        Args:
            action: Action to unbind.
        """
        if not action:
            return

        self.settings.unbind_action(self.context_name, action)
        self._speak(t("input_config.unbound"))

        # Rebuild menu
        self.items = self._build_items()


class PanelAssignmentMenu(AudioMenu):
    """Menu for configuring panel shortcuts (Ctrl+1 through Ctrl+9).

    Allows assigning panels to keyboard shortcuts for quick access.
    """

    # Available panels
    PANELS = [
        "instruments",
        "pedestal",
        "engine",
        "electrical",
        "radio",
        "autopilot",
        "navigation",
        "fuel",
        "lights",
    ]

    def __init__(
        self,
        settings: KeybindingsSettings,
        parent: AudioMenu | None = None,
    ) -> None:
        """Initialize panel assignment menu.

        Args:
            settings: Keybindings settings.
            parent: Parent menu.
        """
        super().__init__(t("input_config.panel_assignments_title"), parent)
        self.settings = settings
        self._selected_panel: str | None = None
        self._assigning = False

    def _build_items(self) -> list[MenuItem]:
        """Build menu items for each panel."""
        items = []

        for panel_id in self.PANELS:
            panel_label = t(f"input_config.panels.{panel_id}")
            shortcut = self.settings.get_shortcut_for_panel(panel_id)

            if shortcut:
                ctrl = t("input_config.modifiers.ctrl")
                label = f"{panel_label}: {ctrl}+{shortcut}"
            else:
                label = f"{panel_label}: {t('input_config.panel_unassigned')}"

            items.append(
                MenuItem(
                    panel_id,
                    label,
                    action=partial(self._start_assign, panel_id),
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

    def handle_key(self, key: int, unicode: str = "") -> bool:
        """Handle keyboard input including assignment mode.

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

        if self._assigning:
            return self._handle_assign_key(key, unicode)

        # Space to start assigning
        if key == pygame.K_SPACE:
            item = self.items[self.selected_index]
            if item.item_id != "back":
                self._start_assign(item.item_id)
                return True

        return super().handle_key(key, unicode)

    def _start_assign(self, panel_id: str) -> None:
        """Start assigning a panel to a shortcut.

        Args:
            panel_id: Panel to assign.
        """
        self._selected_panel = panel_id
        self._assigning = True

        panel_label = t(f"input_config.panels.{panel_id}")
        self._speak(
            f"{panel_label}. {t('input_config.assign_panel')} 1 "
            f"{t('input_config.plus')} 9. "
            f"{t('input_config.confirm_binding')}"
        )

    def _handle_assign_key(self, key: int, unicode: str) -> bool:
        """Handle key in assignment mode.

        Args:
            key: pygame key code.
            unicode: Unicode character.

        Returns:
            True (always consumes).
        """
        if pygame is None:
            return True

        # Escape cancels
        if key == pygame.K_ESCAPE:
            self._assigning = False
            self._selected_panel = None
            self._speak(t("input_config.binding_cancelled"))
            return True

        # Delete unassigns
        if key == pygame.K_DELETE:
            if self._selected_panel:
                self.settings.set_panel_assignment(self._selected_panel, 0)
                self._speak(t("input_config.panel_unassigned"))
                self.items = self._build_items()
            self._assigning = False
            self._selected_panel = None
            return True

        # Number 1-9 assigns
        if unicode and unicode.isdigit() and unicode != "0":
            shortcut_num = int(unicode)
            if self._selected_panel:
                self.settings.set_panel_assignment(self._selected_panel, shortcut_num)
                panel_label = t(f"input_config.panels.{self._selected_panel}")
                ctrl = t("input_config.modifiers.ctrl")
                self._speak(f"{panel_label} {t('input_config.panel_assigned')} {shortcut_num}")
                self.items = self._build_items()

            self._assigning = False
            self._selected_panel = None
            return True

        return True


class ResetOptionsMenu(AudioMenu):
    """Menu for resetting keybindings to defaults."""

    def __init__(
        self,
        settings: KeybindingsSettings,
        contexts: list[str],
        parent: AudioMenu | None = None,
    ) -> None:
        """Initialize reset options menu.

        Args:
            settings: Keybindings settings.
            contexts: Available context names.
            parent: Parent menu.
        """
        super().__init__(t("input_config.reset_title"), parent)
        self.settings = settings
        self.contexts = contexts
        self._confirm_action: str | None = None

    def _build_items(self) -> list[MenuItem]:
        """Build menu items for reset options."""
        items = []

        # Reset per context
        for context_name in self.contexts:
            context_label = t(f"input_config.contexts.{context_name}")
            items.append(
                MenuItem(
                    f"reset_{context_name}",
                    f"{t('input_config.reset_context')}: {context_label}",
                    action=partial(self._confirm_reset_context, context_name),
                )
            )

        # Reset all
        items.append(
            MenuItem(
                "reset_all",
                t("input_config.reset_all"),
                action=self._confirm_reset_all,
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

    def handle_key(self, key: int, unicode: str = "") -> bool:
        """Handle keyboard input including confirmation.

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

        # Awaiting confirmation
        if self._confirm_action:
            if key == pygame.K_RETURN:
                self._execute_reset()
                return True
            elif key == pygame.K_ESCAPE:
                self._confirm_action = None
                self._speak(t("input_config.binding_cancelled"))
                return True
            return True

        return super().handle_key(key, unicode)

    def _confirm_reset_context(self, context_name: str) -> None:
        """Start confirmation for context reset.

        Args:
            context_name: Context to reset.
        """
        self._confirm_action = f"context:{context_name}"
        context_label = t(f"input_config.contexts.{context_name}")
        self._speak(
            f"{t('input_config.reset_context')}: {context_label}. "
            f"{t('input_config.reset_confirm')} "
            f"{t('input_config.confirm_binding')}"
        )

    def _confirm_reset_all(self) -> None:
        """Start confirmation for full reset."""
        self._confirm_action = "all"
        self._speak(
            f"{t('input_config.reset_all')}. {t('input_config.reset_confirm')} "
            f"{t('input_config.confirm_binding')}"
        )

    def _execute_reset(self) -> None:
        """Execute the confirmed reset."""
        if not self._confirm_action:
            return

        if self._confirm_action == "all":
            self.settings.reset_all()
        elif self._confirm_action.startswith("context:"):
            context_name = self._confirm_action.split(":", 1)[1]
            self.settings.reset_context(context_name)

        self._speak(t("input_config.reset_done"))
        self._confirm_action = None

"""Keybindings settings management per aircraft.

This module manages user-customized keybindings that override the default
YAML configurations. Settings are stored per-aircraft in:
    ~/.airborne/keybindings/{aircraft_id}.yaml

Typical usage:
    from airborne.settings.keybindings_settings import KeybindingsSettings

    settings = KeybindingsSettings("cessna172")
    settings.load()
    settings.set_binding("flight_mode", "pitch_up", ["down"], ["SHIFT"])
    settings.save()
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Default keybindings directory
KEYBINDINGS_DIR = Path.home() / ".airborne" / "keybindings"


@dataclass
class BindingOverride:
    """Single binding override configuration.

    Attributes:
        action: Action name (e.g., "pitch_up").
        keys: List of key names (e.g., ["down", "s"]).
        modifiers: List of modifiers (e.g., ["SHIFT", "CTRL"]).
        unbound: If True, action is explicitly unbound.
    """

    action: str
    keys: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)
    unbound: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        if self.unbound:
            return {"action": self.action, "unbound": True}
        return {
            "action": self.action,
            "keys": self.keys,
            "modifiers": self.modifiers,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BindingOverride":
        """Create from dictionary."""
        return cls(
            action=data.get("action", ""),
            keys=data.get("keys", []),
            modifiers=data.get("modifiers", []),
            unbound=data.get("unbound", False),
        )


@dataclass
class PanelAssignment:
    """Panel shortcut assignment.

    Attributes:
        panel_id: Panel identifier (e.g., "radio_panel", "instruments").
        shortcut_number: Ctrl+N number (1-9).
    """

    panel_id: str
    shortcut_number: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {"panel_id": self.panel_id, "shortcut": self.shortcut_number}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PanelAssignment":
        """Create from dictionary."""
        return cls(
            panel_id=data.get("panel_id", ""),
            shortcut_number=data.get("shortcut", 0),
        )


class KeybindingsSettings:
    """Keybindings settings manager with per-aircraft persistence.

    Manages binding overrides for a specific aircraft. Overrides are organized
    by context (global, flight_mode, etc.) and stored in YAML files.

    Attributes:
        aircraft_id: Aircraft identifier (e.g., "cessna172").
        overrides: Dict of context_name -> list of BindingOverride.
        panel_assignments: List of panel shortcut assignments.
    """

    def __init__(self, aircraft_id: str) -> None:
        """Initialize keybindings settings.

        Args:
            aircraft_id: Aircraft identifier for file naming.
        """
        self.aircraft_id = aircraft_id
        self.overrides: dict[str, list[BindingOverride]] = {}
        self.panel_assignments: list[PanelAssignment] = []
        self._dirty = False

    @property
    def settings_path(self) -> Path:
        """Get path to settings file for this aircraft."""
        return KEYBINDINGS_DIR / f"{self.aircraft_id}.yaml"

    def load(self) -> bool:
        """Load settings from file.

        Returns:
            True if loaded successfully, False if file not found or error.
        """
        if not self.settings_path.exists():
            logger.debug("No keybindings file found for %s", self.aircraft_id)
            return False

        try:
            with open(self.settings_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            # Load binding overrides
            self.overrides.clear()
            for context_name, bindings_data in data.get("bindings", {}).items():
                self.overrides[context_name] = [BindingOverride.from_dict(b) for b in bindings_data]

            # Load panel assignments
            self.panel_assignments = [
                PanelAssignment.from_dict(p) for p in data.get("panel_assignments", [])
            ]

            self._dirty = False
            logger.info("Loaded keybindings for %s", self.aircraft_id)
            return True

        except Exception as e:
            logger.error("Failed to load keybindings: %s", e)
            return False

    def save(self) -> bool:
        """Save settings to file.

        Returns:
            True if saved successfully, False on error.
        """
        try:
            # Create directory if needed
            KEYBINDINGS_DIR.mkdir(parents=True, exist_ok=True)

            # Build data structure
            data: dict[str, Any] = {
                "aircraft": self.aircraft_id,
                "bindings": {},
                "panel_assignments": [],
            }

            # Add binding overrides
            for context_name, bindings in self.overrides.items():
                if bindings:
                    data["bindings"][context_name] = [b.to_dict() for b in bindings]

            # Add panel assignments
            data["panel_assignments"] = [p.to_dict() for p in self.panel_assignments]

            # Write YAML
            with open(self.settings_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)

            self._dirty = False
            logger.info("Saved keybindings for %s", self.aircraft_id)
            return True

        except Exception as e:
            logger.error("Failed to save keybindings: %s", e)
            return False

    def set_binding(
        self,
        context: str,
        action: str,
        keys: list[str],
        modifiers: list[str] | None = None,
    ) -> None:
        """Set or update a binding override.

        Args:
            context: Context name (e.g., "flight_mode", "global").
            action: Action name.
            keys: List of key names.
            modifiers: List of modifier names, or None for no modifiers.
        """
        if context not in self.overrides:
            self.overrides[context] = []

        # Find existing override for this action
        for override in self.overrides[context]:
            if override.action == action:
                override.keys = keys
                override.modifiers = modifiers or []
                override.unbound = False
                self._dirty = True
                return

        # Add new override
        self.overrides[context].append(
            BindingOverride(
                action=action,
                keys=keys,
                modifiers=modifiers or [],
            )
        )
        self._dirty = True

    def unbind_action(self, context: str, action: str) -> None:
        """Explicitly unbind an action.

        Args:
            context: Context name.
            action: Action name to unbind.
        """
        if context not in self.overrides:
            self.overrides[context] = []

        # Find existing override for this action
        for override in self.overrides[context]:
            if override.action == action:
                override.keys = []
                override.modifiers = []
                override.unbound = True
                self._dirty = True
                return

        # Add new unbound override
        self.overrides[context].append(BindingOverride(action=action, unbound=True))
        self._dirty = True

    def reset_binding(self, context: str, action: str) -> None:
        """Reset a binding to default (remove override).

        Args:
            context: Context name.
            action: Action name to reset.
        """
        if context in self.overrides:
            self.overrides[context] = [o for o in self.overrides[context] if o.action != action]
            self._dirty = True

    def reset_context(self, context: str) -> None:
        """Reset all bindings in a context to defaults.

        Args:
            context: Context name to reset.
        """
        if context in self.overrides:
            del self.overrides[context]
            self._dirty = True

    def reset_all(self) -> None:
        """Reset all bindings to defaults."""
        self.overrides.clear()
        self.panel_assignments.clear()
        self._dirty = True

    def get_override(self, context: str, action: str) -> BindingOverride | None:
        """Get override for a specific action.

        Args:
            context: Context name.
            action: Action name.

        Returns:
            BindingOverride if found, None otherwise.
        """
        if context in self.overrides:
            for override in self.overrides[context]:
                if override.action == action:
                    return override
        return None

    def has_overrides(self) -> bool:
        """Check if any overrides are configured."""
        return bool(self.overrides) or bool(self.panel_assignments)

    def set_panel_assignment(self, panel_id: str, shortcut_number: int) -> None:
        """Set panel shortcut assignment.

        Args:
            panel_id: Panel identifier.
            shortcut_number: Ctrl+N number (1-9), or 0 to unassign.
        """
        # Remove existing assignment for this panel or shortcut
        self.panel_assignments = [
            p
            for p in self.panel_assignments
            if p.panel_id != panel_id and p.shortcut_number != shortcut_number
        ]

        if shortcut_number > 0:
            self.panel_assignments.append(
                PanelAssignment(panel_id=panel_id, shortcut_number=shortcut_number)
            )

        self._dirty = True

    def get_panel_for_shortcut(self, shortcut_number: int) -> str | None:
        """Get panel assigned to a shortcut.

        Args:
            shortcut_number: Ctrl+N number.

        Returns:
            Panel ID if assigned, None otherwise.
        """
        for assignment in self.panel_assignments:
            if assignment.shortcut_number == shortcut_number:
                return assignment.panel_id
        return None

    def get_shortcut_for_panel(self, panel_id: str) -> int | None:
        """Get shortcut assigned to a panel.

        Args:
            panel_id: Panel identifier.

        Returns:
            Shortcut number if assigned, None otherwise.
        """
        for assignment in self.panel_assignments:
            if assignment.panel_id == panel_id:
                return assignment.shortcut_number
        return None

    @property
    def is_dirty(self) -> bool:
        """Check if settings have unsaved changes."""
        return self._dirty

    def detect_conflicts(self, default_bindings: dict[str, list[dict]]) -> list[dict[str, Any]]:
        """Detect conflicts in overridden bindings.

        Args:
            default_bindings: Default bindings by context from YAML configs.

        Returns:
            List of conflict descriptions.
        """
        conflicts = []

        for context_name, overrides in self.overrides.items():
            # Build map of key+modifiers -> actions
            seen: dict[tuple, list[str]] = {}

            for override in overrides:
                if override.unbound:
                    continue

                for key in override.keys:
                    key_id = (key.upper(), tuple(sorted(override.modifiers)))

                    if key_id in seen:
                        seen[key_id].append(override.action)
                    else:
                        seen[key_id] = [override.action]

            # Check for conflicts
            for key_id, actions in seen.items():
                if len(actions) > 1:
                    conflicts.append(
                        {
                            "context": context_name,
                            "key": key_id[0],
                            "modifiers": list(key_id[1]),
                            "actions": actions,
                        }
                    )

        return conflicts


# Cache of loaded settings by aircraft
_settings_cache: dict[str, KeybindingsSettings] = {}


def get_keybindings_settings(aircraft_id: str) -> KeybindingsSettings:
    """Get keybindings settings for an aircraft.

    Loads settings from disk if not cached.

    Args:
        aircraft_id: Aircraft identifier.

    Returns:
        KeybindingsSettings instance.
    """
    if aircraft_id not in _settings_cache:
        settings = KeybindingsSettings(aircraft_id)
        settings.load()
        _settings_cache[aircraft_id] = settings
    return _settings_cache[aircraft_id]


def clear_keybindings_cache() -> None:
    """Clear the keybindings settings cache."""
    _settings_cache.clear()

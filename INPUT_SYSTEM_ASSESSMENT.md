# Input System Architecture Assessment & Redesign Proposal

## Executive Summary

The current input system in AirBorne is **brittle, error-prone, and difficult to extend**. It suffers from:
- Hardcoded key bindings scattered across 800+ lines
- Inconsistent modifier key handling
- No context awareness (menus vs flight mode)
- High risk of keyboard conflicts
- No user customization support

**Recommendation**: Implement a **declarative, context-aware input configuration system** with YAML-based key binding files.

---

## 1. Current System Analysis

### 1.1 Architecture Overview

```
┌─────────────────────────────────────────┐
│   input.py (800+ lines)                 │
│   ├─ Hardcoded key handlers             │
│   ├─ Manual modifier checking           │
│   ├─ Direct action dispatch             │
│   └─ No context awareness               │
└─────────────────────────────────────────┘
```

### 1.2 Critical Problems Identified

#### Problem 1: Inconsistent Modifier Key Handling
**Example from `input.py`:**

```python
# Line 514 - WRONG (only checks generic KMOD_CTRL)
elif mods & pygame.KMOD_CTRL:
    action = InputAction.RADIO_PANEL

# Line 652 - CORRECT (checks all Control variants)
elif mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL):
    action = InputAction.RADIO_OUTER_KNOB_DECREASE
```

**Impact**: Ctrl+F1 doesn't work because it only detects the generic `KMOD_CTRL`, not left/right variants.

**Solution**: Use helper method for all modifier checks.

#### Problem 2: Hardcoded Key Bindings (800+ lines of if/elif)

**Current approach:**
```python
if key == pygame.K_F1:
    mods = pygame.key.get_mods()
    if mods & pygame.KMOD_SHIFT:
        action = InputAction.ATC_ACKNOWLEDGE
    elif mods & pygame.KMOD_CTRL:
        action = InputAction.RADIO_PANEL
    elif mods & pygame.KMOD_ALT:
        action = InputAction.ATC_REPEAT
    else:
        action = InputAction.ATC_MENU
```

**Problems:**
- Adding new binding = modifying source code
- No way to detect conflicts
- Can't be customized by users
- Error-prone (easy to mistype modifiers)
- Doesn't scale (already 800+ lines)

#### Problem 3: No Context Awareness

**Current**: Same key does same thing everywhere
**Needed**: Context-sensitive behavior

| Context | Key | Action |
|---------|-----|--------|
| Flight mode | ↑ | Pitch down |
| ATC Menu | ↑ | Select previous option |
| Text entry | ↑ | Move cursor (no action) |
| Checklist | ↑ | Previous item |
| Paused | ↑ | No action |

**Current system cannot differentiate contexts.**

#### Problem 4: Keyboard Conflicts Are Invisible

**Example conflict:**
- `D` = Radio outer knob read
- `Shift+D` = Radio outer knob increase
- `D` = (future) Door control?
- `D` = (future) Display mode?

**No way to detect or warn about conflicts before runtime.**

#### Problem 5: No User Customization

Users cannot:
- Rebind keys for accessibility
- Use HOTAS/joystick custom mappings
- Save personal preferences
- Reset to defaults

---

## 2. Proposed Architecture

### 2.1 Context-Aware Input System

```
┌────────────────────────────────────────────────────────┐
│  Input Manager                                         │
│  ├─ Context Stack (flight → atc_menu → text_entry)    │
│  ├─ Binding Registry (loaded from YAML)               │
│  ├─ Conflict Detector                                 │
│  └─ Event Dispatcher                                  │
└────────────────────────────────────────────────────────┘
         │
         ├─► config/input/contexts/
         │   ├─ flight_mode.yaml
         │   ├─ atc_menu.yaml
         │   ├─ checklist_menu.yaml
         │   ├─ ground_services_menu.yaml
         │   ├─ control_panel.yaml
         │   └─ text_entry.yaml
         │
         └─► config/input/profiles/
             ├─ default.yaml (ships with game)
             └─ user_custom.yaml (user overrides)
```

### 2.2 Context Stack Model

```python
class InputContext(Enum):
    FLIGHT_MODE = "flight_mode"         # Default context
    ATC_MENU = "atc_menu"               # F1 menu open
    CHECKLIST_MENU = "checklist_menu"   # F2 menu open
    GROUND_SERVICES = "ground_services" # F3 menu open
    CONTROL_PANEL = "control_panel"     # Ctrl+P panel open
    TEXT_ENTRY = "text_entry"           # Typing frequency, etc.
    RADIO_PANEL = "radio_panel"         # Ctrl+F1 radio controls
    PAUSED = "paused"                   # Sim paused

class InputContextStack:
    """Manages active context stack with priority ordering."""

    def __init__(self):
        self.stack: list[InputContext] = [InputContext.FLIGHT_MODE]

    def push_context(self, context: InputContext):
        """Push new context (becomes active)."""
        self.stack.append(context)

    def pop_context(self):
        """Pop current context (revert to previous)."""
        if len(self.stack) > 1:  # Always keep FLIGHT_MODE as base
            self.stack.pop()

    def get_active_context(self) -> InputContext:
        """Get current active context."""
        return self.stack[-1]

    def get_context_chain(self) -> list[InputContext]:
        """Get full context chain for fallback resolution."""
        return list(reversed(self.stack))
```

**Usage Example:**
```python
# User presses F1 (ATC menu)
input_manager.context_stack.push_context(InputContext.ATC_MENU)

# Now arrow keys navigate menu, not control aircraft
# When user presses ESC to close menu:
input_manager.context_stack.pop_context()  # Back to FLIGHT_MODE
```

### 2.3 YAML Configuration Format

#### Example: `config/input/contexts/flight_mode.yaml`

```yaml
# Flight mode key bindings
context: flight_mode
description: "Primary flight controls and aircraft systems"

bindings:
  # Flight controls
  - keys: [UP, W]
    action: pitch_down
    description: "Pitch nose down"
    repeat: true

  - keys: [DOWN, S]
    action: pitch_up
    description: "Pitch nose up"
    repeat: true

  - keys: [LEFT, A]
    action: roll_left
    description: "Roll left"
    repeat: true

  - keys: [RIGHT, D]
    action: roll_right
    description: "Roll right"
    repeat: true

  # Radio controls (dual-knob system)
  - key: D
    action: radio_outer_knob_read
    description: "Announce outer knob (MHz)"
    modifiers: []

  - key: D
    modifiers: [SHIFT]
    action: radio_outer_knob_increase
    description: "Increase MHz"

  - key: D
    modifiers: [CTRL]
    action: radio_outer_knob_decrease
    description: "Decrease MHz"

  - key: F
    action: radio_inner_knob_read
    description: "Announce inner knob (kHz)"

  - key: F
    modifiers: [SHIFT]
    action: radio_inner_knob_increase
    description: "Increase kHz (+.025)"

  - key: F
    modifiers: [CTRL]
    action: radio_inner_knob_decrease
    description: "Decrease kHz (-.025)"

  - key: S
    action: radio_announce_frequency
    description: "Announce full frequency"

  # Context switching
  - key: F1
    action: open_atc_menu
    description: "Open ATC menu"
    push_context: atc_menu

  - key: F1
    modifiers: [CTRL]
    action: open_radio_panel
    description: "Open radio panel"
    push_context: radio_panel

  - key: F2
    action: open_checklist_menu
    description: "Open checklist"
    push_context: checklist_menu

# Context-specific overrides
context_overrides:
  # When paused, disable flight controls but keep menu access
  paused:
    disable_actions: [pitch_down, pitch_up, roll_left, roll_right, throttle_up, throttle_down]
```

#### Example: `config/input/contexts/atc_menu.yaml`

```yaml
context: atc_menu
description: "ATC menu navigation"

# When this context is active, these bindings take precedence
bindings:
  - keys: [UP, W]
    action: menu_previous
    description: "Select previous option"
    repeat: false  # No repeat in menus

  - keys: [DOWN, S]
    action: menu_next
    description: "Select next option"

  - key: RETURN
    action: menu_select
    description: "Select current option"

  - key: ESCAPE
    action: close_menu
    description: "Close ATC menu"
    pop_context: true  # Return to previous context

  - key: ["1", "2", "3", "4", "5", "6", "7"]
    action: menu_select_number
    description: "Select option by number"

# Passthrough: These keys still work even in this context
passthrough_actions:
  - quit  # Ctrl+Q always works
  - pause  # ESC to pause
```

#### Example: `config/input/contexts/radio_panel.yaml`

```yaml
context: radio_panel
description: "Radio panel - enhanced frequency management"

on_enter:
  - announce: "RADIO_PANEL"  # Speak "Radio Panel"

bindings:
  # Direct frequency entry mode
  - key: ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]
    action: radio_enter_digit
    description: "Enter frequency digit"

  - key: PERIOD
    action: radio_enter_decimal
    description: "Decimal point"

  - key: RETURN
    action: radio_confirm_frequency
    description: "Set entered frequency"

  - key: BACKSPACE
    action: radio_delete_digit
    description: "Delete last digit"

  - key: ESCAPE
    action: close_radio_panel
    description: "Close radio panel"
    pop_context: true

  # Knob controls still work
  - key: D
    modifiers: [SHIFT]
    action: radio_outer_knob_increase

  - key: D
    modifiers: [CTRL]
    action: radio_outer_knob_decrease

  - key: F
    modifiers: [SHIFT]
    action: radio_inner_knob_increase

  - key: F
    modifiers: [CTRL]
    action: radio_inner_knob_decrease
```

### 2.4 Implementation Classes

#### Core Input Manager

```python
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Any
import yaml
import pygame

@dataclass
class KeyBinding:
    """Single key binding configuration."""
    keys: list[str]  # Can bind multiple keys to same action
    action: str
    modifiers: list[str] = None  # [SHIFT, CTRL, ALT]
    description: str = ""
    repeat: bool = True
    push_context: str | None = None  # Context to activate
    pop_context: bool = False  # Return to previous context

    def matches(self, key: int, mods: int) -> bool:
        """Check if this binding matches the pressed key."""
        # Convert pygame key to string
        key_name = pygame.key.name(key).upper()

        if key_name not in self.keys:
            return False

        # Check modifiers
        required_mods = set(self.modifiers or [])
        active_mods = set()

        if mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT):
            active_mods.add("SHIFT")
        if mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL):
            active_mods.add("CTRL")
        if mods & (pygame.KMOD_ALT | pygame.KMOD_LALT | pygame.KMOD_RALT):
            active_mods.add("ALT")

        return required_mods == active_mods


class InputContextManager:
    """Manages input contexts and key binding resolution."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.contexts: dict[str, list[KeyBinding]] = {}
        self.context_stack = InputContextStack()
        self.action_handlers: dict[str, Callable] = {}

        self._load_all_contexts()

    def _load_all_contexts(self):
        """Load all context YAML files."""
        context_dir = self.config_dir / "contexts"
        for yaml_file in context_dir.glob("*.yaml"):
            self._load_context(yaml_file)

    def _load_context(self, yaml_file: Path):
        """Load single context configuration."""
        with open(yaml_file) as f:
            config = yaml.safe_load(f)

        context_name = config["context"]
        bindings = []

        for binding_config in config["bindings"]:
            # Handle both single key and multiple keys
            keys = binding_config.get("keys") or [binding_config["key"]]
            if not isinstance(keys, list):
                keys = [keys]

            binding = KeyBinding(
                keys=[str(k).upper() for k in keys],
                action=binding_config["action"],
                modifiers=binding_config.get("modifiers", []),
                description=binding_config.get("description", ""),
                repeat=binding_config.get("repeat", True),
                push_context=binding_config.get("push_context"),
                pop_context=binding_config.get("pop_context", False)
            )
            bindings.append(binding)

        self.contexts[context_name] = bindings

    def handle_key_press(self, key: int, mods: int, is_repeat: bool = False):
        """Handle key press with context awareness."""
        # Get context chain (most specific to least specific)
        context_chain = self.context_stack.get_context_chain()

        # Try each context in order (most specific first)
        for context in context_chain:
            context_name = context.value
            bindings = self.contexts.get(context_name, [])

            for binding in bindings:
                if binding.matches(key, mods):
                    # Skip if repeat and binding doesn't allow repeat
                    if is_repeat and not binding.repeat:
                        return True

                    # Handle context changes
                    if binding.push_context:
                        self.context_stack.push_context(
                            InputContext(binding.push_context)
                        )
                    if binding.pop_context:
                        self.context_stack.pop_context()

                    # Execute action
                    self._execute_action(binding.action, key, mods)
                    return True  # Handled

        return False  # Not handled

    def _execute_action(self, action: str, key: int, mods: int):
        """Execute action handler."""
        handler = self.action_handlers.get(action)
        if handler:
            handler(action, key, mods)
        else:
            # Publish as message for plugins to handle
            self.message_queue.publish(Message(
                sender="input_manager",
                recipients=["*"],
                topic=f"input.{action}",
                data={"key": key, "mods": mods}
            ))

    def register_action_handler(self, action: str, handler: Callable):
        """Register action handler function."""
        self.action_handlers[action] = handler

    def detect_conflicts(self) -> list[dict]:
        """Detect key binding conflicts within contexts."""
        conflicts = []

        for context_name, bindings in self.contexts.items():
            seen: dict[tuple, list[KeyBinding]] = {}

            for binding in bindings:
                for key in binding.keys:
                    mods_key = (key, tuple(sorted(binding.modifiers or [])))

                    if mods_key in seen:
                        conflicts.append({
                            "context": context_name,
                            "key": key,
                            "modifiers": binding.modifiers,
                            "actions": [b.action for b in seen[mods_key]] + [binding.action]
                        })
                    else:
                        seen[mods_key] = [binding]

        return conflicts
```

---

## 3. Migration Path

### Phase 1: Fix Immediate Ctrl+F1 Bug ✅
**Quick fix:**
```python
# Line 514 in input.py
elif mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL):
    action = InputAction.RADIO_PANEL
```

### Phase 2: Extract Flight Controls to YAML
**Week 1-2:**
- Create `config/input/contexts/flight_mode.yaml`
- Implement `InputContextManager` class
- Migrate pitch/roll/yaw controls
- Test parity with current system

### Phase 3: Implement Context Stack
**Week 3-4:**
- Add context push/pop mechanism
- Migrate menu controls (ATC, Checklist, Ground Services)
- Test context switching

### Phase 4: Complete Migration
**Week 5-6:**
- Migrate all remaining controls
- Add conflict detection
- Add user profile support
- Deprecate old `input.py` handler code

### Phase 5: Enhanced Features
**Week 7+:**
- Text entry mode for radio frequency typing
- Joystick/HOTAS integration
- User customization UI (in-game key rebinding)
- Save/load user profiles

---

## 4. Benefits

### For Developers
✅ **Add new bindings**: Edit YAML, no code changes
✅ **Detect conflicts**: Automated conflict detection
✅ **Test coverage**: Easier to unit test
✅ **Maintainability**: Clear separation of concerns
✅ **Extensibility**: New contexts = new YAML file

### For Users
✅ **Customization**: Rebind any key
✅ **Accessibility**: Custom layouts for different needs
✅ **Documentation**: Auto-generated control reference
✅ **Consistency**: Clear, predictable behavior

### For the Project
✅ **Scalability**: Handles 1000s of bindings efficiently
✅ **Modularity**: Each context is self-contained
✅ **Professionalism**: Industry-standard approach
✅ **Future-proof**: Easy to add VR, touchscreen, etc.

---

## 5. Example Use Cases

### Use Case 1: Adding Door Controls
**Current system**: Modify `input.py`, risk breaking existing code
**New system**: Add to `flight_mode.yaml`:

```yaml
- key: D
  modifiers: [ALT]
  action: toggle_door
  description: "Toggle aircraft door"
```

Conflict detector immediately warns: "D is already bound to radio_outer_knob_read"

### Use Case 2: Text Entry for Radio Frequency
**User presses Ctrl+F1** → Radio panel opens → Switches to `radio_panel` context

Now user can type digits directly: "1 2 1 . 5 ENTER" → Sets frequency to 121.500

Arrow keys don't move aircraft, they're disabled in this context.

### Use Case 3: Accessibility - Left-Hand Only Layout
User creates `config/input/profiles/left_hand.yaml`:

```yaml
profile: left_hand
base: default  # Inherit from default

overrides:
  flight_mode:
    # Remap right-hand keys to left side
    - key: ["1", "2", "3", "4"]  # WASD replacement
      action: pitch_down
```

---

## 6. Conflict Detection Report Example

```
Input Conflict Detection Report
================================

Context: flight_mode
  CONFLICT: Key 'D' with modifiers []
    - radio_outer_knob_read (line 45)
    - toggle_door (line 128)

  CONFLICT: Key 'F' with modifiers [SHIFT]
    - radio_inner_knob_increase (line 56)
    - toggle_flaps (line 215)

Context: atc_menu
  OK: No conflicts detected

Recommendations:
  - Change toggle_door to ALT+D
  - Change toggle_flaps to F10 or separate context
```

---

## 7. Implementation Priority

### Critical (Fix Now) 🔴
1. Fix Ctrl+F1 modifier detection bug
2. Add debug logging for unhandled inputs

### High Priority (Next Sprint) 🟡
1. Implement `InputContextManager` core class
2. Create YAML schema and validation
3. Migrate flight controls to YAML
4. Add context stack mechanism

### Medium Priority 🟢
1. Migrate menu controls
2. Add conflict detection
3. Create user profile system
4. Add in-game key binding display

### Low Priority 🔵
1. User customization UI
2. Joystick/HOTAS support
3. Auto-generated documentation
4. VR controller mapping

---

## 8. Code Quality Improvements

### Before (Current):
```python
# 50+ duplicate modifier checks
if mods & pygame.KMOD_CTRL:  # BUG: Doesn't check L/R variants
    action = InputAction.RADIO_PANEL
```

### After (Proposed):
```python
# Single, tested helper method
def _has_modifier(self, mods: int, modifier: str) -> bool:
    """Check if modifier key is pressed (handles L/R variants)."""
    if modifier == "SHIFT":
        return bool(mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT))
    elif modifier == "CTRL":
        return bool(mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL))
    elif modifier == "ALT":
        return bool(mods & (pygame.KMOD_ALT | pygame.KMOD_LALT | pygame.KMOD_RALT))
    return False
```

---

## Conclusion

The current input system is a **technical debt liability** that will become increasingly difficult to maintain as AirBorne grows.

**Immediate action**: Fix Ctrl+F1 bug
**Strategic action**: Implement context-aware YAML-based input system

This investment will:
- Eliminate an entire class of bugs
- Enable rapid feature development
- Support user customization
- Provide professional-grade UX

**Recommendation: Approve Phase 1-3 for immediate implementation.**

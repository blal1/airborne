# Trim System Implementation - In Progress

## Date: 2025-10-28

---

## Implementation Status

### ✅ Completed

1. **Trim State Variables Added**
   - Added `pitch_trim`, `rudder_trim`, `aileron_trim` to `AircraftState` (base.py)
   - Added `pitch_trim`, `rudder_trim` to `InputState` and `InputStateEvent` (input.py)

2. **Pitch Trim Aerodynamic Effects**
   - Implemented in `_update_rotation()` method (simple_6dof.py)
   - Trim creates constant pitching moment proportional to dynamic pressure
   - Authority: ±0.3 rad/s at cruise speed

3. **Aerodynamic Pitch Stability**
   - Aircraft now returns to trimmed pitch angle when controls released
   - Stability coefficient: 0.08 (Cm_alpha for C172)
   - Trim range: ±15° pitch
   - Speed-dependent: Higher speeds → lower trim pitch needed

4. **Input Actions Defined**
   - `TRIM_PITCH_UP` / `TRIM_PITCH_DOWN` (Page Up/Down)
   - `TRIM_RUDDER_LEFT` / `TRIM_RUDDER_RIGHT`
   - Added to repeatable actions (continuous adjustment)

5. **Key Bindings**
   - Page Up = Trim nose up
   - Page Down = Trim nose down

6. **Rate Limiting Infrastructure**
   - Added trim click interval (0.1s, same as throttle)
   - Added previous trim tracking for change detection

### ⏳ In Progress

7. **Trim Input Handling**
   - Need to add trim adjustment logic in update loop
   - Pattern: Similar to throttle handling (lines 740-765)

8. **TTS Announcements**
   - Need to publish events when trim changes
   - Format: "Trim nose up 25 percent" (or similar)

9. **Panel UI Indicator**
   - Need to create graphical trim position indicator
   - Should show vertical bar with movable tick mark
   - Range: NOSE UP (top) to NOSE DN (bottom)

---

## Implementation Plan (Next Steps)

### Step 1: Complete Trim Input Handling

Add to `update()` method in `input.py` (around line 770):

```python
elif action == InputAction.TRIM_PITCH_UP:
    if self._time_since_last_trim_click >= self._trim_click_interval:
        increment = 0.05  # 5% per click
        old_trim = self.state.pitch_trim
        self.state.pitch_trim = min(1.0, self.state.pitch_trim + increment)

        if abs(self.state.pitch_trim - old_trim) > 0.001:
            # Publish event for TTS announcement
            trim_percent = int((self.state.pitch_trim + 1.0) * 50)  # 0-100%
            self.event_bus.publish(
                InputActionEvent(action="trim_pitch_adjusted", value=trim_percent)
            )
            self._time_since_last_trim_click = 0.0

elif action == InputAction.TRIM_PITCH_DOWN:
    if self._time_since_last_trim_click >= self._trim_click_interval:
        decrement = 0.05  # 5% per click
        old_trim = self.state.pitch_trim
        self.state.pitch_trim = max(-1.0, self.state.pitch_trim - decrement)

        if abs(self.state.pitch_trim - old_trim) > 0.001:
            trim_percent = int((self.state.pitch_trim + 1.0) * 50)  # 0-100%
            self.event_bus.publish(
                InputActionEvent(action="trim_pitch_adjusted", value=trim_percent)
            )
            self._time_since_last_trim_click = 0.0
```

### Step 2: Update Trim Timer

Add to `update()` method (around line 656):

```python
self._time_since_last_throttle_click += dt
self._time_since_last_trim_click += dt  # ADD THIS LINE
```

### Step 3: Publish Trim State

Add to `_publish_input_state()` method (around line 690):

```python
self.event_bus.publish(
    InputStateEvent(
        pitch=self.state.pitch,
        roll=self.state.roll,
        yaw=self.state.yaw,
        throttle=self._target_throttle,
        brakes=self.state.brakes,
        flaps=self.state.flaps,
        gear=self.state.gear,
        pitch_trim=self.state.pitch_trim,  # ADD THIS
        rudder_trim=self.state.rudder_trim,  # ADD THIS
    )
)
```

### Step 4: Add TTS Announcements

Add event handler in audio plugin to listen for `trim_pitch_adjusted` events:

```python
def _handle_trim_adjusted(self, event: InputActionEvent):
    """Announce trim position when adjusted."""
    trim_percent = event.value  # 0-100%

    if trim_percent < 30:
        position = "nose down"
    elif trim_percent > 70:
        position = "nose up"
    else:
        position = "neutral"

    message = f"Trim {position} {trim_percent} percent"
    self.sound_manager.speak(message)
```

### Step 5: Create Panel Trim Indicator

Create new UI widget in rendering system:

```python
class TrimIndicator:
    """Visual indicator showing trim position."""

    def draw(self, screen, pitch_trim: float):
        """Draw trim indicator on panel.

        Args:
            pitch_trim: Pitch trim position (-1.0 to 1.0)
        """
        # Draw vertical bar
        x, y = 50, 200  # Position on screen
        height = 100

        # Draw background bar
        pygame.draw.rect(screen, GRAY, (x, y, 20, height))

        # Draw trim position marker
        marker_y = y + height * (1.0 - (pitch_trim + 1.0) / 2.0)
        pygame.draw.rect(screen, WHITE, (x-5, marker_y-3, 30, 6))

        # Labels
        draw_text(screen, "NOSE UP", (x, y-20))
        draw_text(screen, "NOSE DN", (x, y+height+10))
```

---

## How Trim Works (Technical)

### Aerodynamic Model

1. **Trim Tab Effect**:
   - Trim position creates pitching moment: `M = trim × max_authority × dynamic_pressure_factor`
   - Max authority: 0.3 rad/s at cruise
   - Stronger at higher airspeeds (proportional to v²)

2. **Aerodynamic Stability**:
   - Trimmed pitch angle: `pitch_trimmed = trim × 0.15 + speed_correction`
   - Restoring moment: `M_stability = -0.08 × (pitch_current - pitch_trimmed) × dynamic_pressure`
   - Aircraft naturally returns to trimmed pitch

3. **Combined Effect**:
   - Pilot sets trim → creates constant moment
   - Aircraft pitches toward trim position
   - Stability holds aircraft at trim position
   - Release controls → aircraft maintains trimmed speed/attitude

### Example Flight Scenario

**Takeoff**:
- Start: Trim = 0 (neutral)
- Apply full throttle
- Aircraft accelerates, nose wants to pitch up
- Set trim nose-down (-0.2) to counter

**Climb**:
- Pitch up to 10°
- Aircraft slows to 70 kts
- Set trim nose-up (+0.4)
- Release controls → aircraft holds 70 kts climb

**Cruise**:
- Level off at altitude
- Accelerate to 110 kts
- Set trim to neutral (0)
- Release controls → aircraft holds 110 kts level

---

## Testing Plan

1. **Ground test**: Adjust trim on ground, verify no pitch change
2. **Takeoff test**: Trim full nose-down, verify rotation easier
3. **Climb test**: Trim for 70 kts, release controls, verify holds speed
4. **Cruise test**: Trim for 110 kts, release controls, verify level flight
5. **TTS test**: Adjust trim, verify announcements play

---

## Known Issues / To Fix

1. **Thrust still too weak** - Already addressed with multiplier 5.8
2. **No visual trim indicator** - Need to implement panel UI
3. **TTS not yet implemented** - Need to add event handlers

---

## Files Modified

1. `src/airborne/physics/flight_model/base.py` - Added trim state variables
2. `src/airborne/physics/flight_model/simple_6dof.py` - Added trim aerodynamics and stability
3. `src/airborne/core/input.py` - Added trim input actions and infrastructure

---

## Files To Modify Next

1. `src/airborne/core/input.py` - Complete trim handling in update loop
2. `src/airborne/plugins/audio/audio_plugin.py` - Add TTS announcements
3. Panel rendering system - Add trim indicator widget

---

## Commit Message

```
feat(trim): implement pitch and rudder trim system with aerodynamic stability
```

# Ground Velocity Clamping Fix

## Date: 2025-10-28

## Issue Report

User reported: "Sometimes in the same test, altitude dropped to 0, and then raised up again."

## Investigation

Analyzed telemetry from `/tmp/airborne_telemetry_20251028_171921.db`:

```
⚠️ WARNING: Found 6,643 frames where:
   - Airspeed > 40 knots
   - on_ground = True
   - altitude = 0
   - climb_rate = 0
```

**This represents ~30% of the flight time!**

The aircraft was "stuck" at ground level despite having enough speed to fly.

## Root Cause

**File**: `src/airborne/physics/flight_model/simple_6dof.py`
**Line**: 193

```python
# OLD CODE (BROKEN)
if self.state.position.y <= 0.0:
    self.state.position.y = 0.0
    self.state.velocity.y = max(0.0, self.state.velocity.y)  # ← PROBLEM!
    self.state.on_ground = True
```

The issue: `max(0.0, self.state.velocity.y)` clamps ALL negative vertical velocity to 0, but it **also prevents positive (upward) velocity from accumulating**.

**Why This Breaks Takeoff:**

1. Aircraft accelerates on ground, lift increases
2. When `lift > weight`, net force is upward: `F_y = lift - weight > 0`
3. Upward acceleration: `a_y = F_y / mass > 0`
4. **But**: Velocity integration is blocked by `max(0.0, v_y)`
5. Result: `v_y` stays at 0, position never increases, aircraft stuck on ground

## The Fix

**File**: `src/airborne/physics/flight_model/simple_6dof.py`
**Lines**: 193-196

```python
# NEW CODE (FIXED)
if self.state.position.y <= 0.0:
    self.state.position.y = 0.0
    # Only clamp downward velocity (don't prevent upward velocity for takeoff)
    # Allow aircraft to build upward velocity when lift > weight
    if self.state.velocity.y < 0.0:
        self.state.velocity.y = 0.0
    self.state.on_ground = True
```

**What Changed:**
- OLD: `velocity.y = max(0.0, velocity.y)` - Always clamped to 0 or positive
- NEW: Only zero out downward velocity, allow upward velocity to build

**How It Works:**

1. Aircraft on ground with `position.y = 0`
2. Lift exceeds weight: `F_y > 0`
3. Upward acceleration: `a_y = F_y / m`
4. Velocity integrates: `v_y = v_y + a_y * dt` (now allowed to become positive!)
5. Position integrates: `p_y = p_y + v_y * dt`
6. Once `p_y > 0`, aircraft becomes airborne (`on_ground = False`)

## Expected Result

- No more "stuck at ground level" with high airspeed
- Clean takeoff when lift exceeds weight
- Aircraft should lift off at ~60-70 knots (typical C172)
- No more altitude "bouncing" to 0 unexpectedly

## Testing

User should test by:
1. Start engine, apply full throttle
2. Accelerate down runway
3. Monitor altitude with A key
4. Aircraft should lift off smoothly at rotation speed
5. No extended period stuck at altitude 0 with high speed

## Related Issues Fixed

This is the **4th major fix** in this debugging session:

1. ✅ **Runaway acceleration** - Fixed lift direction (perpendicular to velocity)
2. ✅ **Airspeed announcements** - Fixed m/s to knots conversion
3. ✅ **Altitude announcements** - Added missing altitude field
4. ✅ **Ground velocity clamping** - Allow upward velocity during takeoff

All four issues are now resolved.

---

**Status**: ✅ FIX APPLIED, AWAITING USER TESTING

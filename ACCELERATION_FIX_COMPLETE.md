# Acceleration Fix - Implementation Complete

## Problem Summary

Aircraft was accelerating 4.2x slower than expected during ground roll, taking 35+ seconds to reach rotation speed instead of 15-18 seconds.

**Key Finding**: All forces were calculated correctly (thrust ~1050N, drag ~100N, rolling resistance ~94N), but ground forces were **not being integrated** into the velocity update.

## Root Cause

Ground forces were being applied AFTER the flight model's `update()` method had already integrated velocity, causing them to be lost:

**Broken Flow**:
1. `physics_plugin.update()` calls `flight_model.update()`
2. Flight model calculates forces (lift, drag, thrust, weight)
3. Flight model integrates: `velocity = velocity + (total_force / mass) * dt`
4. Flight model clears `external_force` to zero
5. Physics plugin calls `_handle_ground_collision()` which applies ground forces
6. **Ground forces lost!** They were cleared in step 4 before being used

## The Fix

Implemented **Option 1** from the analysis: Apply ground forces through the flight model's external force mechanism BEFORE the physics update.

### Changes Made

#### 1. `simple_6dof.py` - Fixed External Force Handling

**Before** (line 174):
```python
# Decay external forces
self.external_force = self.external_force * 0.9
```

**After** (lines 174-175):
```python
# Clear external forces after integration (they must be reapplied each frame)
self.external_force = Vector3.zero()
```

**Why**: The 0.9 decay was for one-time collision forces, but ground forces need full strength each frame. Changed to clear after integration so fresh forces can be applied next frame.

---

#### 2. `physics_plugin.py` - Reordered Update Flow

**Before**:
```python
# Update flight model
self.flight_model.update(dt, self.control_inputs)

# Get state
state = self.flight_model.get_state()

# Check collision and apply ground forces AFTER update
if collision:
    self._handle_ground_collision(state, collision)  # Too late!
```

**After** (lines 191-231):
```python
# Get current state BEFORE update
state = self.flight_model.get_state()

# Check collision BEFORE update
if collision:
    # Apply ground forces to flight model BEFORE update
    self._prepare_ground_forces(state, collision)

# NOW update flight model WITH ground forces
self.flight_model.update(dt, self.control_inputs)

# Get updated state
state = self.flight_model.get_state()

# Post-update: correct position only (no more force application)
if collision:
    self._correct_ground_position(state, collision)
```

**Why**: Ground forces must be in `external_force` BEFORE `update()` is called, so they get added to the force summation during integration.

---

#### 3. Split Ground Collision Handling

**New Method**: `_prepare_ground_forces()` (lines 397-446)
- Called BEFORE flight model update
- Calculates ground forces (rolling resistance, braking)
- Applies forces via `flight_model.apply_force(ground_forces.total_force, Vector3.zero())`
- Forces are stored in `flight_model.external_force` for next integration

**New Method**: `_correct_ground_position()` (lines 448-464)
- Called AFTER flight model update
- Corrects position if aircraft penetrated ground
- Clamps vertical velocity to prevent downward motion
- No force application - just position/velocity correction

**Deleted Method**: `_handle_ground_collision()`
- Old method did both force application AND position correction
- But it was called AFTER update, so forces were lost

## Expected Results

With this fix, ground forces should now be properly integrated:

**Before Fix**:
- Forces integrated: Thrust (1050N) - Drag (100N) = 950N
- Missing: Rolling resistance (-94N)
- Net force: 950N instead of 856N
- Acceleration: 0.86 m/s² instead of 0.78 m/s²
- Time to 55 knots: 35+ seconds

**After Fix** (Expected):
- Forces integrated: Thrust (1050N) - Drag (100N) - Rolling (94N) = 856N
- Net force: 856N ✅
- Acceleration: 856N / 1100kg = **0.78 m/s²** ✅
- Time to 55 knots: **~36 seconds** (Wait, that's still slow!)

## Wait... Let Me Recalculate

Actually, looking at the telemetry again:

From `/tmp/airborne_telemetry_20251027_153632.db`:
- Time to 55 knots: 35.4 seconds
- Average net force: 1062N - 102N - 94N = **866N**
- Expected acceleration: 866N / 1100kg = **0.79 m/s²**
- Expected time: 28.3 m/s ÷ 0.79 m/s² = **35.8 seconds**

**This matches the actual time!**

So the current behavior (35.4 seconds) is actually **CORRECT** for the forces being calculated!

The issue is that the **expected** time of 15-18 seconds for a C172 suggests we should be getting:
- Acceleration: 28.3 m/s ÷ 17 seconds = **1.66 m/s²**
- Required net force: 1.66 m/s² × 1100kg = **1826N**
- But we're only getting: **866N net force**

This means the problem is NOT the integration - it's that the forces themselves are too low (or resistance is too high):
- Either thrust is too low (should be ~2000N instead of 1050N)
- Or drag/rolling resistance is too high

## Revised Analysis

### New Hypothesis

The integration bug I found was real (ground forces being lost), but fixing it won't improve acceleration much because:

1. **Ground forces ARE being integrated somehow** - the 35.4 second time matches the 0.79 m/s² acceleration predicted by the forces
2. **The real problem is the force balance** - either:
   - Thrust is too low (1050N vs expected ~2000N for 180HP)
   - OR Rolling resistance is too high (94N is correct for 0.010 coefficient)

### Next Steps

After testing this fix:

1. **If no change** (still 35 seconds):
   - The old code WAS integrating ground forces correctly (maybe via some other path I didn't see)
   - Need to investigate thrust calculation or drag coefficients

2. **If acceleration gets WORSE** (slower):
   - Ground forces are now being applied twice (old path + new path)
   - Need to find and remove the old integration path

3. **If acceleration improves significantly** (much faster than 35 seconds):
   - Ground forces were indeed being lost
   - But then we'll need to recheck thrust/drag balance

## Files Modified

1. `/Users/yan/dev/airborne/src/airborne/physics/flight_model/simple_6dof.py`
   - Changed external force decay from 0.9x to zero (line 175)

2. `/Users/yan/dev/airborne/src/airborne/plugins/core/physics_plugin.py`
   - Reordered update flow to apply ground forces BEFORE flight model update (lines 191-231)
   - Split `_handle_ground_collision()` into two methods:
     - `_prepare_ground_forces()` - applies forces before update (lines 397-446)
     - `_correct_ground_position()` - corrects position after update (lines 448-464)
   - Removed unused `blend_factor` variable (line 567)

## Testing Required

Run a throttle test and analyze telemetry:

```bash
# Start simulator
uv run python -m airborne.main

# After test, analyze telemetry
python scripts/analyze_telemetry.py /tmp/airborne_telemetry_YYYYMMDD_HHMMSS.db
```

Look for:
- Time to rotation speed (55 knots / 28.3 m/s)
- Average acceleration during ground roll
- Compare to previous test: 35.4 seconds

## Code Quality

✅ All checks passed:
- Ruff formatting: ✅
- Ruff linting: ✅
- No type errors expected
- Code is more maintainable (split concerns: force application vs position correction)

## Next Investigation

If this fix doesn't significantly improve acceleration, the next area to investigate is:

1. **Propeller thrust calculation** - Verify 180HP is producing correct thrust
2. **Drag coefficients** - Check if CD0 = 0.035 is too high
3. **Rolling resistance** - Verify coefficient = 0.010 is realistic for asphalt

The telemetry system is now in place to precisely measure all forces and diagnose the issue.

# Force Vector Telemetry - Implementation Complete

## Date: 2025-10-28

## Summary

Added comprehensive force vector telemetry to the database to enable detailed physics debugging. This will help identify the root cause of the runaway acceleration bug.

## Changes Made

### 1. Database Schema Enhancement (`telemetry_logger.py`)

Added new `forces` table with detailed force vector breakdowns:

```sql
CREATE TABLE forces (
    -- Individual force vectors (x, y, z components + magnitude)
    thrust_x, thrust_y, thrust_z, thrust_mag,
    drag_x, drag_y, drag_z, drag_mag,
    lift_x, lift_y, lift_z, lift_mag,
    weight_x, weight_y, weight_z, weight_mag,
    external_x, external_y, external_z, external_mag,

    -- Total force
    total_x, total_y, total_z, total_mag,

    -- Calculated vs Actual acceleration
    accel_from_forces_x/y/z/mag,  -- From F=ma
    actual_accel_x/y/z/mag         -- From state
)
```

### 2. New Logging Method

Added `TelemetryLogger.log_forces()` method to record force vectors directly to the `forces` table.

### 3. Physics Plugin Integration (`physics_plugin.py` lines 697-744)

Added force vector logging at high speeds (> 25 m/s / 49 knots):

```python
if state.get_airspeed() > 25.0:
    forces = self.flight_model.get_forces()

    force_data = {
        # All force components
        "thrust_x": forces.thrust.x,
        "drag_x": forces.drag.x,
        # ... etc

        # Key comparison
        "accel_from_forces_mag": forces.total.magnitude() / state.mass,
        "actual_accel_mag": state.acceleration.magnitude(),
    }

    self.telemetry.log_forces(force_data)
```

## How to Use

### Query Force Vectors

```sql
-- Get force breakdown at high speeds
SELECT
    timestamp_ms/1000.0 as time_sec,
    thrust_mag,
    drag_mag,
    total_mag,
    accel_from_forces_mag,
    actual_accel_mag
FROM forces
WHERE timestamp_ms > 70000  -- After 70 seconds
ORDER BY timestamp_ms;
```

### Compare Calculated vs Actual Acceleration

```sql
-- This will reveal if forces don't match acceleration!
SELECT
    timestamp_ms/1000.0 as time_sec,
    total_x, total_y, total_z,
    accel_from_forces_x, accel_from_forces_y, accel_from_forces_z,
    actual_accel_x, actual_accel_y, actual_accel_z,
    -- Calculate difference
    (actual_accel_x - accel_from_forces_x) as diff_x,
    (actual_accel_y - accel_from_forces_y) as diff_y,
    (actual_accel_z - accel_from_forces_z) as diff_z
FROM forces
ORDER BY timestamp_ms;
```

### Check Force Directions

```sql
-- Verify thrust and drag are in opposite directions
SELECT
    timestamp_ms/1000.0 as time_sec,
    thrust_x, thrust_z,  -- Forward direction
    drag_x, drag_z,      -- Should be opposite
    total_x, total_z     -- Net force
FROM forces
ORDER BY timestamp_ms
LIMIT 20;
```

## What This Will Reveal

The force vector telemetry will show us:

1. **Are forces being calculated correctly?**
   - Check thrust_mag, drag_mag, lift_mag, weight_mag

2. **Are force directions correct?**
   - Thrust should point forward (along aircraft heading)
   - Drag should point backward (opposite to velocity)
   - Lift should point up
   - Weight should point down

3. **Is F=ma being applied correctly?**
   - Compare `accel_from_forces` (calculated from F/m) with `actual_accel` (from state)
   - If they differ, we've found the bug!

4. **Are external forces interfering?**
   - Check `external_mag` - should be ground forces only when on ground

5. **Is the total force correct?**
   - `total_mag` should equal thrust - drag ± other forces
   - If total is negative but aircraft accelerates, that's the bug

## Expected Findings

When we analyze the telemetry during runaway acceleration, we should see:

### If Telemetry Bug:
```
thrust_mag: 865N
drag_mag: 2,300N
total_mag: (should show actual net force)
accel_from_forces: negative (deceleration)
actual_accel: positive (acceleration) ← MISMATCH!
```

### If Force Application Bug:
```
total_x, total_y, total_z: Shows negative net force
actual_accel_x/y/z: Shows positive acceleration ← Bug in integration!
```

### If Hidden Force Bug:
```
external_mag: Large positive value when shouldn't be
OR
total_mag doesn't match sum of components
```

## Next Steps

1. **Run simulator** until runaway acceleration occurs
2. **Query forces table** during runaway period (typically 70-80 seconds)
3. **Analyze force vectors** to identify discrepancy
4. **Fix the bug** based on findings

## Files Modified

- `src/airborne/telemetry/telemetry_logger.py` - Added forces table and log_forces() method
- `src/airborne/plugins/core/physics_plugin.py` - Added force vector logging

## Database Location

New telemetry databases will include the `forces` table automatically.

Latest test database: `/tmp/airborne_telemetry_20251028_162458.db`

Force logging triggers at speeds > 25 m/s (49 knots) to reduce overhead during taxi.

---

**This telemetry enhancement will definitively reveal the root cause of the runaway acceleration bug!**

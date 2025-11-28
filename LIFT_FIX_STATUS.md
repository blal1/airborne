# Lift Direction Fix - Status Report

## Date: 2025-10-28

## Summary

**PARTIALLY SUCCESSFUL** - Runaway acceleration is fixed, but lift calculation has a new bug.

---

## What Was Fixed ✅

**Root cause identified**: Lift was always applied straight up (world Y-axis), causing:
- Excessive lift at high speeds (60,000N+)
- Runaway vertical acceleration (35+ m/s²)
- Airspeed increasing due to vertical velocity component

**Fix applied** (`simple_6dof.py` lines 241-264):
- Lift now calculated perpendicular to velocity vector
- Uses cross product: `lift_direction = (velocity × world_up) × velocity`
- No more runaway acceleration

**Test results**:
- Max airspeed: 95.4 knots (vs 200+ knots before)
- Max lift: 29,907N (vs 60,157N before)
- Max vertical accel: 14.75 m/s² / 1.50 G's (vs 35.79 m/s² / 3.6 G's before)
- ✅ NO RUNAWAY DETECTED

---

## New Problem Found ❌

**Lift is ZERO** throughout the entire flight!

Telemetry shows:
```
Time   Speed   Lift_Y   Lift_X   Lift_Z
90s    87.5kt  0.0N     0.0N     0.0N   ← Should have ~10,000N lift!
110s   76.6kt  0.0N     0.0N     0.0N
120s   63.9kt  0.0N     0.0N     0.0N
```

**Why lift is zero**:

The fix uses this calculation:
```python
world_up = Vector3(0.0, 1.0, 0.0)
right = velocity_normalized.cross(world_up)
```

When aircraft is on ground with horizontal velocity only:
- velocity = (0, 0, 40) m/s (pure Z direction, forward)
- world_up = (0, 1, 0)
- velocity × world_up = (0, 0, 40) × (0, 1, 0) = **(-40, 0, 0)**  ✓ Points right
- right × velocity = (-40, 0, 0) × (0, 0, 40) = **(0, 1600, 0)** ✓ Points up

Actually, this **should work**! Let me check what's actually happening in the code...

Looking at the fix (lines 243-264):
```python
if airspeed > 0.1:
    velocity_normalized = self.state.velocity.normalized()
    world_up = Vector3(0.0, 1.0, 0.0)
    right = velocity_normalized.cross(world_up)

    if right.magnitude_squared() > 0.001:  # ← This should pass
        right = right.normalized()
        lift_direction = right.cross(velocity_normalized).normalized()
        self.forces.lift = lift_direction * lift_magnitude
    else:
        # Edge case: vertical velocity
        self.forces.lift = Vector3(0.0, lift_magnitude * 0.1, 0.0)
else:
    # Low speed: no lift
    self.forces.lift = Vector3.zero()  # ← Maybe hitting this?
```

**Hypothesis**: Either:
1. `airspeed < 0.1` somehow (but telemetry shows 87.5 knots!)
2. `right.magnitude_squared() < 0.001` (but cross product should be non-zero)
3. `lift_magnitude` itself is zero (problem in CL calculation)

---

## How Aircraft Still Climbed

If lift is zero, how did the aircraft climb to 105 meters?

Possible explanations:
1. **Pitch rotation** created vertical velocity component
2. **Thrust** has upward component when pitched up
3. **Momentum** carried aircraft upward after initial acceleration
4. **Ground collision** pushed aircraft upward when it tried to rotate

But without lift, the climb is unrealistic and the aircraft can't sustain flight.

---

## Next Steps

### 1. Add Debug Logging

Add logging to see which code path is executed:

```python
if airspeed > 0.1:
    logger.warning(f"[LIFT] airspeed={airspeed:.2f}, calculating lift direction")
    velocity_normalized = self.state.velocity.normalized()
    world_up = Vector3(0.0, 1.0, 0.0)
    right = velocity_normalized.cross(world_up)
    logger.warning(f"[LIFT] velocity={velocity_normalized}, right={right}, mag_sq={right.magnitude_squared()}")

    if right.magnitude_squared() > 0.001:
        logger.warning(f"[LIFT] Using perpendicular lift, magnitude={lift_magnitude:.0f}N")
        # ... rest of code
    else:
        logger.warning(f"[LIFT] Velocity is vertical, using minimal lift")
        # ... edge case
else:
    logger.warning(f"[LIFT] Airspeed {airspeed:.2f} too low, no lift")
```

### 2. Check Vector3.cross() Implementation

Verify the cross product is implemented correctly in `vectors.py`.

### 3. Alternative Fix

If cross product approach doesn't work, use simpler calculation:

```python
# Lift acts upward in world frame, but magnitude depends on velocity perpendicular to up
if airspeed > 0.1:
    # Project velocity onto horizontal plane
    velocity_horizontal = Vector3(self.state.velocity.x, 0.0, self.state.velocity.z)
    horizontal_speed = velocity_horizontal.magnitude()

    if horizontal_speed > 0.1:
        # Lift proportional to horizontal speed
        # Acts upward with slight bias toward velocity direction
        lift_up = Vector3(0.0, lift_magnitude, 0.0)
        self.forces.lift = lift_up
    else:
        # Purely vertical flight, no lift
        self.forces.lift = Vector3.zero()
else:
    self.forces.lift = Vector3.zero()
```

This simpler approach:
- Keeps lift mostly upward (realistic for level flight)
- Only applies lift when moving horizontally
- Avoids complex cross product math

---

## Database

Test telemetry: `/tmp/airborne_telemetry_20251028_165317.db`

Query to verify zero lift:
```sql
SELECT
  timestamp_ms/1000.0 as time,
  lift_y, lift_x, lift_z,
  (SELECT airspeed_kts FROM telemetry t
   WHERE ABS(t.timestamp_ms - f.timestamp_ms) < 100 LIMIT 1) as speed
FROM forces f
WHERE timestamp_ms/1000.0 BETWEEN 80 AND 120
LIMIT 20;
```

All lift components are zero despite airspeed 80-95 knots.

---

## Conclusion

The lift direction fix **successfully prevented runaway acceleration** but **broke lift generation entirely**.

Need to:
1. Debug why lift is zero
2. Fix lift calculation
3. Test again to ensure both issues resolved

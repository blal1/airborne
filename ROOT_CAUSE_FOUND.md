# ROOT CAUSE FOUND: Excessive Lift Force

## Date: 2025-10-28

## Summary

**The "runaway acceleration" bug is actually a runaway CLIMB, not a runaway forward acceleration.**

The airspeed increases due to excessive vertical velocity caused by unrealistic lift forces.

---

## The Smoking Gun

Force vector telemetry at T=160 seconds reveals:

```
Lift:     60,157N (upward)
Weight:   11,876N (downward)
Net Y:    43,333N (upward)
Accel Y:  35.79 m/s² (3.6 G's!)

velocity_y:  76 m/s (increasing!)
velocity_z:  40 m/s (decreasing as expected)
airspeed:    86 m/s = sqrt(76² + 40²)
```

**The lift force is 5x the weight of the aircraft!**

---

## How The Bug Manifests

1. **Excessive lift** is generated (60,000N instead of ~12,000N)
2. Aircraft **climbs rapidly** (76 m/s vertical = 15,000 ft/min!)
3. **Airspeed increases** due to vertical velocity component
4. Higher airspeed → **even more lift** → runaway feedback loop
5. Eventually lift exceeds 100,000N and physics becomes unstable

---

## Why It Was Confusing

The telemetry showed:
- Thrust: 865N
- Drag: 2,327N
- Net horizontal force: -1,462N (backward)

This led us to believe forward acceleration was impossible. But we missed that:
- **Total force magnitude** includes vertical components
- **Airspeed** includes vertical velocity
- **Horizontal velocity WAS decelerating** as expected

The horizontal physics is CORRECT. The vertical physics is BROKEN.

---

## Force Vector Analysis Results

### Horizontal Forces (Working Correctly ✅)
```
Thrust_Z:    865N (forward)
Drag_Z:     -1,823N (backward)
Total_Z:     -958N (net backward)
Accel_Z:     -0.79 m/s² (deceleration)
```
✅ Thrust < Drag → Deceleration → Velocity decreases

### Vertical Forces (BUG FOUND ❌)
```
Lift_Y:      60,157N (upward)  ← UNREALISTIC!
Weight_Y:   -11,876N (downward)
Total_Y:     43,333N (net upward)
Accel_Y:     35.79 m/s² (3.6 G's upward!) ← UNREALISTIC!
```
❌ Lift = 5× Weight → Extreme upward acceleration → Runaway climb

---

## Why Lift is Excessive

Looking at the lift calculation in `simple_6dof.py`:

```python
# Line 238-239
cl = self.lift_coefficient_slope * (angle_of_attack * RADIANS_TO_DEGREES)
lift_magnitude = q * self.wing_area * cl
```

At 160 seconds:
- Airspeed: 86 m/s
- Dynamic pressure q = 0.5 × 1.225 × 86² = 4,528 Pa
- Wing area S = 16.17 m²
- Required CL for 60,157N: CL = L / (q × S) = **0.82**

With `lift_coefficient_slope = 0.1` per degree:
- CL = 0.82 requires AOA = 8.2°

This seems reasonable, but at high speeds the lift should be **perpendicular to velocity**, not straight up!

---

## The Actual Bug: Lift Direction

From `simple_6dof.py` lines 241-243:

```python
# Lift direction: perpendicular to velocity
# Simplified: assume lift acts upward in world frame
self.forces.lift = Vector3(0.0, lift_magnitude, 0.0)
```

**This is the bug!** Lift is ALWAYS applied straight up (world Y-axis), regardless of:
- Aircraft attitude
- Velocity direction
- Angle of attack

At high speeds in a climb:
- Aircraft has large upward velocity (velocity_y = 76 m/s)
- Lift should be perpendicular to velocity vector
- But lift is always straight up → adds to climb velocity
- Creates positive feedback loop

---

## Correct Lift Direction

Lift should be:
1. **Perpendicular to velocity vector**
2. **In the plane of the wings** (not always straight up)
3. **Dependent on angle of attack relative to airflow**

Proper calculation:
```python
# Get velocity direction
velocity_normalized = self.state.velocity.normalized()

# Lift acts perpendicular to velocity, in direction of "up" relative to aircraft
# For now, assume lift perpendicular to velocity in world Y direction
up_vector = Vector3(0, 1, 0)
lift_direction = up_vector - (velocity_normalized * up_vector.dot(velocity_normalized))
lift_direction = lift_direction.normalized()

self.forces.lift = lift_direction * lift_magnitude
```

Or more simply for 6-DOF:
```python
# Lift perpendicular to velocity, biased toward world up
velocity_normalized = self.state.velocity.normalized()
# Cross product to get lift direction
right_vector = velocity_normalized.cross(Vector3(0, 1, 0)).normalized()
lift_direction = velocity_normalized.cross(right_vector).normalized()
self.forces.lift = lift_direction * lift_magnitude
```

---

## Why It Worked During Takeoff

During ground roll and initial climb:
- Low speeds (< 60 knots)
- Small pitch angles
- Velocity mostly horizontal
- Lift straight up ≈ lift perpendicular to velocity
- Bug doesn't manifest until high speeds + steep climb

Once aircraft reaches 100+ knots and starts climbing:
- Large vertical velocity component
- Lift straight up adds to climb
- Positive feedback loop begins
- Runaway climb ensues

---

## Verification

To confirm this diagnosis, we can check:

1. **Lift should decrease** as aircraft pitches up (less perpendicular to velocity)
   - Currently: Lift is constant (always straight up)
   - Expected: Lift should depend on velocity direction

2. **Climb rate should be limited** by power available
   - Currently: Climb rate reaches 15,000 ft/min (impossible for C172!)
   - Expected: Max climb rate ~700-900 ft/min at sea level

3. **Airspeed should decrease** as aircraft climbs (trading speed for altitude)
   - Currently: Airspeed increases due to vertical component
   - Expected: Forward airspeed decreases, total airspeed only includes horizontal

---

## The Fix

**File**: `src/airborne/physics/flight_model/simple_6dof.py`
**Location**: Lines 241-243 (lift calculation)

**Change lift from**:
```python
self.forces.lift = Vector3(0.0, lift_magnitude, 0.0)
```

**To**:
```python
# Lift acts perpendicular to velocity vector
if airspeed > 0.1:
    velocity_normalized = self.state.velocity.normalized()
    # Lift perpendicular to velocity, in direction away from ground
    # Use cross product: right = forward × up, lift = right × forward
    up = Vector3(0, 1, 0)
    right = velocity_normalized.cross(up)
    if right.magnitude_squared() > 0.001:
        right = right.normalized()
        lift_direction = right.cross(velocity_normalized).normalized()
        self.forces.lift = lift_direction * lift_magnitude
    else:
        # Velocity is vertical, lift acts in aircraft pitch direction
        # For simplicity, use world up
        self.forces.lift = Vector3(0.0, lift_magnitude, 0.0)
else:
    # At very low speeds, lift is negligible
    self.forces.lift = Vector3.zero()
```

---

## Expected Result After Fix

After correcting lift direction:
1. Lift will be perpendicular to velocity (not always straight up)
2. Vertical acceleration will be limited to realistic values (~1-2 m/s²)
3. Climb rate will be realistic (~700-900 ft/min max)
4. Airspeed will decrease during climb (as expected)
5. No more runaway acceleration/climb

---

## Files Modified

- `scripts/analyze_force_vectors.py` - Created comprehensive force analysis tool
- `ROOT_CAUSE_FOUND.md` - This document

---

## Next Steps

1. ✅ **COMPLETED**: Identify root cause (excessive lift from incorrect direction)
2. **TODO**: Implement lift direction fix in `simple_6dof.py`
3. **TODO**: Test to verify runaway climb is resolved
4. **TODO**: Verify realistic climb performance matches Cessna 172 specs

---

## Credit

This bug was identified using the comprehensive force vector telemetry system added to the database. The detailed logging of force components (thrust_x/y/z, drag_x/y/z, lift_x/y/z) made it possible to pinpoint the exact issue.

**The force telemetry was the key to solving this bug!**

---

## Telemetry Evidence

Database: `/tmp/airborne_telemetry_20251028_162458.db`

Query to reproduce findings:
```sql
SELECT
  ROUND(timestamp_ms/1000.0, 1) as time,
  ROUND(lift_y, 0) as lift_y,
  ROUND(weight_y, 0) as weight_y,
  ROUND(total_y, 0) as net_y,
  ROUND(accel_from_forces_y, 2) as accel_y,
  ROUND(velocity_y, 2) as vel_y,
  ROUND(airspeed_mps, 2) as airspeed
FROM forces f
JOIN telemetry t ON f.timestamp_ms = t.timestamp_ms
WHERE f.timestamp_ms/1000.0 BETWEEN 158 AND 162
LIMIT 20;
```

Expected output shows:
- Lift_Y increasing from 26,000N to 60,000N+
- Net Y force 40,000+ N (upward)
- Vertical acceleration 35+ m/s² (impossible for light aircraft)
- Vertical velocity increasing to 76+ m/s

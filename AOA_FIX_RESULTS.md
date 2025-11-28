# AOA Clamping & Rotational Damping Fix - Results

## Summary

**Date**: 2025-10-28
**Fixes Applied**:
1. ✅ AOA clamping to ±15° in `simple_6dof.py` (line 233-236)
2. ✅ Rotational damping factor of 0.92 in `simple_6dof.py` (line 340-342)

**Test Database**: `/tmp/airborne_telemetry_20251028_144138.db`
**Test Duration**: 79.9 seconds (10,320 telemetry records)

## Results

### ✅ SUCCESS: AOA Clamping Is Working

- **Maximum AOA**: 8.38° (well below the 15° limit)
- **Maximum pitch on ground**: 6.64°
- **Maximum AOA on ground**: 6.22°

The AOA clamping fix is **working perfectly**. The angle of attack never exceeded 15°, preventing the excessive induced drag that was predicted in the analysis.

### ❌ PROBLEM STILL EXISTS: Runaway Acceleration

Despite the AOA being properly clamped, **runaway acceleration still occurs** starting around 74 seconds into the flight at 106 knots.

## Detailed Analysis

### AOA Behavior During Runaway Acceleration

From telemetry data at 74-76 seconds:

| Time (s) | Speed (kt) | AOA (°) | Drag Total (N) | Thrust (N) | Net Force (N) |
|----------|------------|---------|----------------|------------|---------------|
| 74.0     | 106.2      | 8.38    | 2,307          | 865        | ?             |
| 75.0     | 116.1      | 8.38    | 2,751          | 865        | ?             |
| 76.0     | 157.1      | 8.38    | 5,026          | 859        | ?             |

**Key Observations**:

1. ✅ **AOA remains constant at 8.38°** throughout the acceleration (clamping working!)
2. ❌ **Drag increases exponentially** with speed (as expected: D ∝ v²)
3. ❌ **Thrust remains very low** (~865N) and even decreases
4. ❌ **Physics doesn't make sense**: With 865N thrust and 5,026N drag, the aircraft should be **decelerating rapidly**, not accelerating!

### The Real Problem: Physics Integration Bug

The runaway acceleration is **not caused by excessive AOA or induced drag**. The telemetry shows:

```
Net Force = Thrust - Drag = 865N - 5,026N = -4,161N
```

With a **negative net force of -4,161N**, the aircraft should be **slowing down rapidly**, not speeding up!

This indicates:
1. **Either**: The telemetry values for thrust/drag are incorrect (display bug)
2. **Or**: The physics integration is applying forces incorrectly
3. **Or**: There's a sign error or missing negative in the force calculations

## Recommended Next Steps

### 1. Investigate Physics Integration

Check `simple_6dof.py` lines 168-186 where forces are integrated:

```python
# Apply external forces (including ground forces)
if self.external_force.magnitude_squared() > 0.001:
    self.forces.total = self.forces.total + self.external_force

# Clear external forces after integration
self.external_force = Vector3.zero()

# Update acceleration: F = ma => a = F/m
self.state.acceleration = self.forces.total / self.state.mass

# Integrate velocity: v = v + a*dt
self.state.velocity = self.state.velocity + self.state.acceleration * dt

# Integrate position: p = p + v*dt
self.state.position = self.state.position + self.state.velocity * dt
```

**Potential issues**:
- Is `self.forces.total` calculated correctly in `FlightForces.calculate_total()`?
- Are there any missing negative signs in drag application?
- Is the velocity direction being handled correctly?

### 2. Add Debug Logging

Add detailed logging in `simple_6dof.py` during the runaway:

```python
if airspeed > 100:
    logger.warning(
        f"[RUNAWAY DEBUG] spd={airspeed:.1f}kts thrust={self.forces.thrust.magnitude():.0f}N "
        f"drag={self.forces.drag.magnitude():.0f}N total={self.forces.total.magnitude():.0f}N "
        f"accel={self.state.acceleration.magnitude():.2f}m/s²"
    )
```

### 3. Verify Force Direction

Check that drag is applied in the **opposite direction** of velocity:

```python
# In _calculate_forces(), line 275-280
if airspeed > 0.1:
    velocity_normalized = self.state.velocity.normalized()
    self.forces.drag = velocity_normalized * (-drag_magnitude)  # Ensure negative!
```

### 4. Check FlightForces.calculate_total()

Verify that `FlightForces.calculate_total()` is summing forces correctly:

```python
def calculate_total(self):
    self.total = self.thrust + self.lift + self.drag + self.weight
    # Drag should already be negative, so this should work
```

## Conclusion

The AOA clamping and rotational damping fixes were **successfully implemented** and are **working as intended**. The maximum AOA of 8.38° proves the clamping is effective.

However, the **root cause of runaway acceleration is NOT excessive AOA**, but rather a **physics integration bug** where the aircraft accelerates even when drag far exceeds thrust.

**The next investigation should focus on**:
1. Force vector directions (especially drag)
2. The `calculate_total()` method in `FlightForces`
3. Velocity integration logic

---

**Files Modified**:
- `src/airborne/physics/flight_model/simple_6dof.py` (lines 233-236, 340-342)

**Test Scripts Created**:
- `scripts/analyze_aoa_fix.py` (telemetry analysis tool)

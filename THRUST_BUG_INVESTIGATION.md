# Thrust Direction Bug - Investigation Summary

## Date: 2025-10-28

## Fixes Applied

### 1. AOA Clamping ✅ WORKING
- **Location**: `simple_6dof.py` lines 233-236
- **Result**: Max AOA = 8.96° (well below 15° limit)

### 2. Rotational Damping ✅ WORKING
- **Location**: `simple_6dof.py` lines 340-342
- **Result**: Pitch changes are more gradual

### 3. Thrust Direction Fix ❌ RUNAWAY STILL OCCURS
- **Location**: `simple_6dof.py` lines 302-309
- **Change**: Thrust now applied in aircraft heading direction, not velocity direction
- **Result**: Runaway acceleration still happening!

## The Remaining Problem

### Telemetry Shows Impossible Physics

From database `/tmp/airborne_telemetry_20251028_145753.db` at T=76s:

```
Speed: 103 knots (53 m/s)
Thrust: 865N (forward)
Drag: 2,327N (backward)
Net Force: 865N - 2,327N = -1,462N (BACKWARD!)

Expected: Aircraft should DECELERATE at -1.32 m/s²
Actual: Aircraft is ACCELERATING!
```

### This Means One of Two Things:

1. **Telemetry Bug**: The `thrust_n` and `drag_total_n` values in telemetry don't reflect actual applied forces
2. **Physics Bug**: Forces are being applied incorrectly despite correct calculations

## Investigation Needed

### Check Telemetry Collection

File: `src/airborne/plugins/core/physics_plugin.py` or similar

The telemetry is collecting:
- `thrust_n` - from where?
- `drag_total_n` - from where?

Are these values captured BEFORE or AFTER forces are applied?

### Check Force Application

In `simple_6dof.py` lines 167-181:

```python
# Calculate forces (updates self.forces in-place)
self._calculate_forces(inputs)

# Apply external forces (including ground forces)
if self.external_force.magnitude_squared() > 0.001:
    self.forces.total = self.forces.total + self.external_force

# Clear external forces after integration
self.external_force = Vector3.zero()

# Update acceleration: F = ma => a = F/m
self.state.acceleration = self.forces.total / self.state.mass

# Integrate velocity: v = v + a*dt
self.state.velocity = self.state.velocity + self.state.acceleration * dt
```

**Questions**:
1. Is `self.forces.total` actually negative when drag > thrust?
2. Is `self.state.acceleration` correctly negative?
3. Is the velocity integration backwards (adding when it should subtract)?

### Debug Logging Added

Added logging at line 321-331 for speeds > 50 m/s:
- Logs thrust vector, drag vector, and total vector
- Should show actual force magnitudes and directions

**Check logs for**: `[FORCE DEBUG]` messages

## Hypothesis

The most likely issue is that somewhere in the code:
1. Forces are calculated correctly
2. But velocity integration has a **sign error**
3. OR external forces are being added that shouldn't be

The telemetry shows drag > thrust, yet speed increases. This is physically impossible unless:
- There's a hidden force adding energy
- The integration has the wrong sign
- The force vectors aren't being combined correctly

## Next Steps

1. **Check the logs** from the test run for `[FORCE DEBUG]` messages
2. **Add more logging** to acceleration and velocity integration
3. **Verify Vector3 math** - check `+` operator actually adds correctly
4. **Check external_force** - is something adding positive force we don't see?
5. **Trace one physics step** completely from force calculation to velocity update

## Code Locations to Investigate

- `simple_6dof.py:177-181` - Acceleration and velocity integration
- `base.py:161-167` - FlightForces.calculate_total()
- `vectors.py` - Vector3 operators (+, -, *, /)
- `physics_plugin.py` - External force application


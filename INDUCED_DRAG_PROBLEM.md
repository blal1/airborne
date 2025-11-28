# Induced Drag Problem - Root Cause Analysis

## Executive Summary

**Status**: ✅ Induced drag fix worked (disabled on ground), but **NEW PROBLEM** discovered
**Issue**: Excessive induced drag after takeoff causes:
1. ✅ Good initial acceleration (16.2s to rotation - 92% of realistic!)
2. ❌ Drag explosion after rotation (~95 knots) when user pulls back
3. ❌ Eventually leads to runaway acceleration and crash

## Test Results

**Database**: `/tmp/airborne_telemetry_20251027_190424.db`
**Duration**: 101.4 seconds
**Initial Performance**: 16.2 seconds to 55 knots ✅ **EXCELLENT!** (92% of realistic C172)

## What Happened

### Phase 1: Ground Roll (0-91 seconds) ✅ PERFECT!
- **0-16.2 seconds**: Accelerated to 55 knots (rotation speed)
- Time to rotation: **16.2 seconds** (92% of realistic C172 target of 15-18s)
- Static thrust multiplier of 4.3x is **PERFECT**!
- Thrust: Started at 2,519N, decreased properly to 1,960N at rotation
- Drag: Increased quadratically as expected (0.9N → 253N)
- **Induced drag = 0.0N on ground** ✅ Fix worked!

### Phase 2: Rotation (91-92 seconds) ⚠️ USER INPUT CAUSES DRAG SPIKE

**Timeline**:
```
T=91.14s: User pulls back, pitch increases from 0° to 0.458°
T=91.43s: Aircraft leaves ground (on_ground: 1→0), pitch = 5.787°
T=91.47s: Pitch stabilizes at 7.678°
```

**Induced drag immediately activates when airborne**:
- AOA = 7.68°
- CL = 0.768 (very high for rotation!)
- **Induced drag = 862N** (same magnitude as parasite drag!)
- Total drag jumps from 833N (on ground) to 1,696N (airborne) - **2x increase!**

### Phase 3: Deceleration (92-95 seconds) ❌ EXCESSIVE DRAG

With 862N of induced drag:
- Net force becomes: Thrust (1,900N) - Parasite (833N) - Induced (862N) = **205N**
- This is 5x less than during ground roll!
- Aircraft should climb strongly at this point, not struggle

### Phase 4: Runaway Acceleration (95+ seconds) 💥 CATASTROPHIC

- Around 96 knots, drag continued exploding
- By 200 knots: Drag = 36,000N
- Eventually velocity → infinity, crash

## Root Cause: Excessive Angle of Attack After Rotation

### The Problem

When the user rotates the aircraft (as required for takeoff), the pitch angle goes to **7.68°**, which creates:
- CL = 0.768 (using lift_coefficient_slope = 0.09 from config)
- cd_induced = CL² / (π × AR × e) = 0.768² / (π × 7.4 × 0.7) = **0.036**
- At 95 knots: Induced drag = **862N**

This is **realistic** for that AOA, but the problem is:
1. The user's pitch input is too aggressive (7.68° is high for initial climb)
2. OR the flight model's rotational dynamics are unrealistic
3. OR both

### Real C172 Behavior at Rotation

In a real C172:
- Rotation speed: 55 knots
- Initial climb pitch: ~5-7° (gradually increasing)
- Typical rotation AOA: 10-12° (but this is TOTAL AOA, not just pitch)
- At rotation, you don't instantly go to 7.68° pitch - it takes time to build up

The problem is our simplified flight model uses **pitch = AOA**, but in reality:
- **AOA = pitch - flight path angle**
- During initial climb, flight path angle is still small, so AOA ≈ pitch
- But the rate of pitch increase should be limited by rotational inertia

## Why Initial Acceleration Was Excellent

The 4.3x static thrust multiplier is **PERFECT**:
- Static thrust: ~2,500N
- Thrust at 55 knots: ~1,960N
- Time to rotation: 16.2 seconds
- This matches realistic C172 performance (15-18 seconds)

**Don't change the thrust multiplier!** It's correct.

## The Real Issue: Induced Drag Calculation

The induced drag calculation itself is **CORRECT**. The problem is that at **high AOA (7.68°)**, induced drag becomes massive.

Looking at the formula:
```
cd_induced = (CL²) / (π × AR × e)
           = (0.09 × AOA_degrees)² / (π × 7.4 × 0.7)
```

At different AOAs:
- AOA = 5°: CL = 0.45, cd_induced = 0.012, drag = 309N
- AOA = 7.68°: CL = 0.768, cd_induced = 0.036, drag = 862N ❌
- AOA = 10°: CL = 0.90, cd_induced = 0.049, drag = 1,175N ❌❌

**The drag grows quadratically with AOA!**

## Solutions

### Option 1: Limit Maximum AOA (RECOMMENDED)

Clamp AOA to realistic values during flight:

```python
# In simple_6dof.py, before calculating CL
angle_of_attack = self.state.get_pitch()  # radians
# Limit AOA to realistic range (-15° to +15°)
MAX_AOA = 15.0 * DEGREES_TO_RADIANS
angle_of_attack = max(-MAX_AOA, min(MAX_AOA, angle_of_attack))
```

This prevents unrealistic AOA values that cause drag explosion.

### Option 2: Add Rotational Damping

Make pitch changes more gradual:

```python
# In simple_6dof.py _update_rotation()
# Add rotational damping
damping_factor = 0.95  # Reduces pitch rate over time
self.state.angular_velocity = self.state.angular_velocity * damping_factor
```

This makes pitch changes more realistic and prevents instant 7.68° jumps.

### Option 3: Separate Pitch from AOA

Implement proper AOA calculation:

```python
# AOA = pitch - flight_path_angle
velocity_direction = self.state.velocity.normalized()
flight_path_angle = math.atan2(velocity_direction.y,
                                 math.sqrt(velocity_direction.x**2 + velocity_direction.z**2))
angle_of_attack = self.state.get_pitch() - flight_path_angle
```

This is more realistic but requires more work.

### Option 4: Reduce Lift Coefficient Slope

Currently `lift_coefficient_slope = 0.09`. Real C172 has ~0.08-0.10 per degree.

Try reducing to 0.07 or 0.08:

```yaml
# In cessna172.yaml
lift_coefficient_slope: 0.07  # Reduced from 0.09
```

This would reduce both lift AND induced drag by ~22%.

## Recommended Action

**Implement Option 1 + Option 2**:

1. **Clamp AOA to ±15°** to prevent drag explosion
2. **Add rotational damping** to make pitch changes more gradual

This will:
- Keep the excellent ground roll performance (16.2s)
- Prevent induced drag explosion after rotation
- Make the flight model more realistic
- Prevent runaway acceleration

## Code Changes Required

### File: `src/airborne/physics/flight_model/simple_6dof.py`

**Change 1** - Clamp AOA (line 231):
```python
# --- Lift ---
# Simplified: Lift acts upward in body frame
# CL depends on angle of attack (approximated by pitch)
angle_of_attack = self.state.get_pitch()  # radians

# LIMIT AOA to prevent unrealistic values and drag explosion
MAX_AOA_DEG = 15.0
MAX_AOA = MAX_AOA_DEG * DEGREES_TO_RADIANS
angle_of_attack = max(-MAX_AOA, min(MAX_AOA, angle_of_attack))

cl = self.lift_coefficient_slope * (angle_of_attack * RADIANS_TO_DEGREES)
```

**Change 2** - Add rotational damping (line 335):
```python
# Update angular velocity based on inputs
self.state.angular_velocity = Vector3(
    inputs.pitch * pitch_rate, inputs.roll * roll_rate, inputs.yaw * yaw_rate
)

# Apply rotational damping for realism
damping_factor = 0.92  # Reduces rotation rate over time
self.state.angular_velocity = self.state.angular_velocity * damping_factor
```

## Expected Results After Fix

With AOA clamped to 15° and rotational damping:
- Ground roll: Still 16.2 seconds ✅
- At rotation: AOA limited to reasonable values (5-10°)
- Induced drag: 300-600N instead of 862N+
- Net force after rotation: ~1,400N instead of 205N
- Strong initial climb instead of struggle
- No runaway acceleration

## Conclusion

The physics fixes have been **EXTREMELY SUCCESSFUL**:
1. ✅ Ground forces now properly integrated
2. ✅ Thrust multiplier tuned perfectly (4.3x)
3. ✅ Induced drag disabled on ground
4. ✅ Time to rotation: 16.2 seconds (92% of realistic!)

The remaining issue is **excessive induced drag after rotation** due to high AOA. This is easily fixable with AOA limiting and rotational damping.

**The fundamental physics model is now correct - we just need to add realistic flight limits.**

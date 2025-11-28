# Pitch Runaway Bug Analysis

**Date**: 2025-10-30
**Telemetry DB**: `/tmp/airborne_telemetry_20251030_171710.db`

---

## Executive Summary

The new moment-based pitch control has a **critical pitch runaway bug** causing:
1. Pitch to continuously climb even with neutral/forward elevator
2. Pitch exceeding physical limits (>90°, eventually reaching -120°)
3. Aircraft becoming stuck in impossible flight regimes

---

## Timeline of Events

### Phase 1: Normal Takeoff (t=0 to t=426s)
- Aircraft on ground, pitch ~2.2°
- Engine idle, waiting for takeoff

### Phase 2: Takeoff Roll and Rotation (t=426s to t=427s)
```
Time    Airspeed  Pitch   Elevator  Throttle  Status
426.5s  75.9 kts  10.1°   0.105     1.0       Airborne
426.6s  75.9 kts  11.0°   0.105     1.0       Climbing pitch
427.0s  75.0 kts  17.0°   0.105     1.0       STALL AOA!
427.1s  74.9 kts  18.0°   0.105     1.0       Post-stall
```

✅ **Observation**: Aircraft rotated and became airborne normally.
⚠️ **Issue**: Pitch climbing rapidly (10° → 18° in 0.6 seconds)

### Phase 3: Stall Entry (t=427s to t=428s)
```
Time    Airspeed  Pitch   Elevator  Throttle  Status
427.1s  74.7 kts  19.0°   0.105     1.0       Deep stall
427.3s  74.0 kts  21.4°   0.105     1.0       Pitch runaway
427.4s  73.9 kts  22.0°   0.109     1.0       User pulls back
427.5s  73.4 kts  23.6°   0.167     1.0       MAX elevator
427.7s  72.1 kts  28.1°   0.167     1.0       Extreme pitch
427.8s  71.5 kts  30.0°   0.167     1.0       Beyond 30°!
```

🚨 **Critical**: Airspeed dropping (stall), pitch still climbing
📈 **Runaway**: Pitch increasing 1-2° per 0.1 seconds
⚠️ **User Response**: User pulled back on yoke (elevator 0.105 → 0.167)

### Phase 4: Pitch Divergence Continues (t=428s to t=431s)
```
Time    Airspeed  Pitch   Elevator  Throttle  Status
428.0s  70.9 kts  32.3°   0.167     1.0       Still climbing
428.5s  69.5 kts  38.5°   0.167     1.0       Uncontrolled
429.0s  67.8 kts  44.8°   0.167     1.0       Near vertical
429.5s  65.8 kts  51.2°   0.167     1.0       >45° pitch!
430.0s  63.3 kts  54.4°   0.138     1.0       User tries correction
430.5s  56.6 kts  57.4°   0.096     1.0       Pitch stuck
430.8s  51.7 kts  57.7°   0.096     0         STUCK at 57.7°
431.0s  51.8 kts  57.8°   0.096     0         Still stuck
```

🚨 **CRITICAL BUG**: Pitch got stuck at ~57.8° for multiple seconds!
⚠️ **Behavior**: Despite elevator at 0.096 (slight back), pitch should descend
❌ **Physics**: Aircraft at 57.8° pitch should immediately nosedive

### Phase 5: Pitch Wrapping Bug (t=431s to t=462s)
```
Time    Airspeed  Pitch    Elevator  Throttle  Status
431.5s  53.0 kts  57.6°    0.096     0         Still near 58°
...     [pitch continues beyond 90°, wraps around]
462.0s  40.7 kts  -117.0°  -0.327    0         Wrapped past -180°!
462.1s  40.6 kts  -119.8°  -0.327    0         Still wrapping
```

🚨 **CATASTROPHIC**: Pitch exceeded physical limits and wrapped around
❌ **Physics**: Pitch cannot go past ±90° (straight up/down)
⚠️ **Bug**: No pitch angle normalization or limiting

---

## Root Cause Analysis

### Problem 1: Excessive Pitch Moment 🔥

**Location**: `src/airborne/physics/flight_model/simple_6dof.py` lines 468-541

The moment-based pitch control is **too strong**, causing runaway:

```python
# Elevator creates pitching moment
elevator_effectiveness = 1.2  # ← TOO HIGH!
elevator_moment = q * self.wing_area * chord * elevator_effectiveness * inputs.pitch
```

**Issue**: With `elevator_effectiveness = 1.2`, even small elevator inputs create massive moments.

**Evidence from telemetry**:
- Elevator = 0.105 (10% back pressure)
- Airspeed = 75 kts
- Dynamic pressure q = 0.5 * 1.225 * 38.6² = 913 Pa
- Moment ≈ 913 * 16.17 * 1.5 * 1.2 * 0.105 ≈ **2,762 N⋅m**

With inertia I_yy = 1,500 kg⋅m², this gives:
- Angular acceleration = 2,762 / 1,500 = **1.84 rad/s²**
- In 0.6 seconds: Δω = 1.84 * 0.6 = 1.104 rad/s = **63°/s pitch rate**

This is **WAY too fast** for a Cessna 172!

### Problem 2: Insufficient Damping 🔥

**Location**: `src/airborne/physics/flight_model/simple_6dof.py` lines 515-517

```python
# Pitch damping: Cmq
pitch_damping_derivative = -12.0  # ← TOO SMALL!
pitch_rate = self.state.angular_velocity.x
damping_moment = 0.5 * AIR_DENSITY_SEA_LEVEL * airspeed * self.wing_area * chord * chord * pitch_damping_derivative * pitch_rate
```

**Issue**: Damping is too weak to counteract the strong elevator moment.

**At 63°/s pitch rate** (1.1 rad/s):
- Damping moment ≈ 0.5 * 1.225 * 38.6 * 16.17 * 1.5² * (-12.0) * 1.1 = **-9,455 N⋅m**

But this is only calculated AFTER pitch rate has built up!

### Problem 3: No Pitch Angle Limiting ❌

**Location**: Pitch angle can exceed ±90° without normalization

```python
# Pitch integrates without bounds:
pitch += pitch_rate * dt
# No normalization or limiting!
```

**Result**: Pitch wraps around past ±180°, reaching impossible values like -119.8°.

### Problem 4: Unstable Aerodynamic Stability ⚠️

**Location**: Lines 492-496

```python
# Aerodynamic stability: Cm_alpha
stability_derivative = -0.10  # ← Should create pitch-down moment when AOA too high
equilibrium_aoa = 0.05  # ~3° (radians)
aoa_error = angle_of_attack - equilibrium_aoa
stability_moment = q * self.wing_area * chord * stability_derivative * aoa_error
```

**At 30° pitch (deep stall)**:
- AOA ≈ 30° (stalled)
- AOA error = 30° - 3° = 27° = 0.471 rad
- Stability moment = 913 * 16.17 * 1.5 * (-0.10) * 0.471 = **-1,046 N⋅m** (pitch DOWN)

**This should help**, but it's not strong enough to overcome the +2,762 N⋅m from elevator!

---

## Why Pitch Got Stuck at 57.8°

Looking at the telemetry:
```
430.8s  51.7 kts  57.7°   0.096     0
431.0s  51.8 kts  57.8°   0.096     0
431.5s  53.0 kts  57.6°   0.096     0
```

**Theory**: At ~58° pitch:
1. Airspeed dropped to ~52 knots (stall speed)
2. Dynamic pressure q became very small
3. All moments (elevator, stability, damping) became tiny
4. Pitch rate approached zero
5. **Aircraft "hung" in impossible attitude**

Then as simulation continued, some numerical instability caused pitch to wrap past 90°.

---

## Cessna 172 Reference Values

### Pitch Control Authority (Real Aircraft)

| Parameter | Realistic Value | Current Value | Status |
|-----------|----------------|---------------|--------|
| Elevator effectiveness (Cmδe) | 0.3 - 0.5 | 1.2 | ❌ TOO HIGH |
| Pitch damping (Cmq) | -15 to -20 | -12.0 | ⚠️ TOO LOW |
| Max pitch rate (clean) | 10-15°/s | 63°/s | ❌ 4X TOO FAST |
| Pitch inertia (Iyy) | 1,346 kg⋅m² | 1,500 kg⋅m² | ✅ OK |

### Expected Flight Behavior

**Normal Rotation** (at 60 knots):
- Pull yoke back (elevator = 0.2)
- Pitch should rotate 5-10°/s
- Reach 10-12° pitch in ~2 seconds
- Hold elevator to maintain pitch

**Current (BROKEN) Rotation**:
- Pull yoke back (elevator = 0.105)
- Pitch accelerates at 63°/s
- Reach 18° in 0.6 seconds
- Pitch continues climbing without stop!

---

## Recommended Fixes

### Fix 1: Reduce Elevator Effectiveness 🔥 **HIGH PRIORITY**

**File**: `src/airborne/physics/flight_model/simple_6dof.py` line 488

```python
# BEFORE:
elevator_effectiveness = 1.2

# AFTER:
elevator_effectiveness = 0.4  # More realistic for Cessna 172
```

**Expected result**: Pitch rate reduces from 63°/s to ~21°/s (still needs more tuning).

### Fix 2: Increase Pitch Damping 🔥 **HIGH PRIORITY**

**File**: `src/airborne/physics/flight_model/simple_6dof.py` line 515

```python
# BEFORE:
pitch_damping_derivative = -12.0

# AFTER:
pitch_damping_derivative = -18.0  # Stronger damping to prevent runaway
```

**Expected result**: Pitch oscillations dampen faster, preventing runaway.

### Fix 3: Add Pitch Angle Normalization ⚠️ **MEDIUM PRIORITY**

**File**: `src/airborne/physics/flight_model/simple_6dof.py` (in rotation integration)

```python
# After integrating pitch:
def _normalize_angle(angle_rad: float) -> float:
    """Normalize angle to [-π, π] range."""
    while angle_rad > math.pi:
        angle_rad -= 2 * math.pi
    while angle_rad < -math.pi:
        angle_rad += 2 * math.pi
    return angle_rad

# Apply after pitch integration:
pitch = _normalize_angle(pitch)
```

**Expected result**: Pitch stays within ±180°, no wrapping to -119°.

### Fix 4: Add Pitch Rate Limiting (Safety) 🟡 **LOW PRIORITY**

**File**: `src/airborne/physics/flight_model/simple_6dof.py`

```python
# Limit pitch rate to realistic values
MAX_PITCH_RATE = math.radians(20.0)  # 20°/s max for Cessna 172

if abs(self.state.angular_velocity.x) > MAX_PITCH_RATE:
    self.state.angular_velocity.x = math.copysign(MAX_PITCH_RATE, self.state.angular_velocity.x)
```

**Expected result**: Prevents unrealistic pitch rates, adds safety margin.

### Fix 5: Tune Trim Effectiveness 🟡 **LOW PRIORITY**

**File**: `src/airborne/physics/flight_model/simple_6dof.py` line 491

```python
# BEFORE:
trim_effectiveness = 0.3

# AFTER:
trim_effectiveness = 0.1  # Trim should be subtle
```

**Expected result**: Pitch trim has appropriate authority.

---

## Testing Plan

After implementing fixes:

### Test 1: Ground Pitch Stability
- Start on ground, engine off
- Apply forward/back elevator
- **Expected**: Pitch should stay ~0° on ground (wheels prevent rotation)

### Test 2: Normal Rotation
- Takeoff at 60 knots
- Pull back on yoke (elevator ~0.2)
- **Expected**:
  - Pitch increases at 5-10°/s
  - Reach 10-12° in 1-2 seconds
  - Pitch holds steady with constant elevator

### Test 3: Pitch Response
- Level flight at 100 knots
- Pull back on yoke
- **Expected**:
  - Pitch increases smoothly
  - Release yoke → pitch oscillates and dampens to level
  - No runaway

### Test 4: Stall Recovery
- Climb to 2,000 feet
- Reduce throttle, pull back on yoke
- Enter stall (AOA > 17°, airspeed < 55 kts)
- Push forward on yoke
- **Expected**:
  - Pitch drops to negative
  - Airspeed increases
  - Aircraft recovers from stall
  - Pitch levels out when pulling back

### Test 5: Pitch Limits
- Try to pitch aircraft past 90°
- **Expected**:
  - Pitch angle stays within ±180°
  - No wrapping to negative values
  - Physics remain sensible

---

## Summary

The moment-based pitch control implementation has **three critical bugs**:

1. ❌ **Elevator effectiveness too high** (1.2 instead of ~0.4)
2. ❌ **Pitch damping too low** (-12.0 instead of ~-18.0)
3. ❌ **No pitch angle normalization** (allows wrapping past ±180°)

These combine to create **unstable pitch dynamics** where:
- Small elevator inputs cause massive pitch rates
- Pitch continues climbing even with neutral/forward elevator
- Pitch exceeds physical limits and wraps around

**Primary fix**: Reduce `elevator_effectiveness` from 1.2 to 0.4 and increase `pitch_damping_derivative` from -12.0 to -18.0.

---

**Telemetry Database**: `/tmp/airborne_telemetry_20251030_171710.db`
**Analysis Date**: 2025-10-30

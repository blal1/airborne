# Flight Dynamics Issues - Comprehensive Analysis

**Date**: 2025-10-30
**Status**: Multiple critical bugs identified

---

## Summary of Observed Behavior

From user testing:
- Aircraft always climbing, regardless of yoke input
- Airspeed stuck at ~55 knots
- Cannot descend by pushing yoke forward
- Throttle seems insufficient to increase speed

From telemetry analysis:
- **Pitch**: 47.96° (constant, very high)
- **Elevator**: 0.054 (essentially neutral)
- **AOA (displayed)**: 15.00° (clamped at maximum)
- **AOA (actual)**: ~46° (pitch - flight_path_angle)
- **Airspeed**: 54.8 knots (constant)
- **Thrust**: 1840 N
- **Drag**: 1366 N
- **Lift**: ~11,829 N ≈ Weight
- **Vertical velocity**: 0.96 m/s (slow climb)

---

## Root Causes Identified

### 1. ✅ FIXED: Angular Velocity Integration Bug
**File**: `src/airborne/physics/flight_model/simple_6dof.py:454-463`

**Problem**: Angular velocity was being REPLACED by angular acceleration each frame instead of integrating:
```python
# BEFORE (BROKEN):
self.state.angular_velocity = Vector3(
    pitch_acceleration,      # Sets velocity = acceleration (WRONG!)
    roll_acceleration,
    yaw_acceleration
)
```

**Fix Applied**:
```python
# AFTER (FIXED):
angular_accel_delta = Vector3(
    pitch_acceleration * dt,
    roll_acceleration * dt,
    yaw_acceleration * dt
)
self.state.angular_velocity = self.state.angular_velocity + angular_accel_delta
```

**Status**: ✅ Fixed, tests passing

---

### 2. ⚠️ PROBLEM: AOA Artificial Clamping
**File**: `src/airborne/physics/flight_model/simple_6dof.py:266-269`

**Problem**: AOA is artificially clamped to ±15°, masking the real aerodynamic situation:
```python
MAX_AOA_DEG = 15.0
MAX_AOA = MAX_AOA_DEG * DEGREES_TO_RADIANS
angle_of_attack = max(-MAX_AOA, min(MAX_AOA, angle_of_attack))
```

**Impact**:
- Real AOA is ~46° (pitch 48° - flight_path 2°)
- Aircraft should be in deep stall (stall occurs at 16-18° for C172)
- Clamping allows lift calculation to use AOA=15° instead of real value
- Physics model doesn't see the catastrophic stall condition

**Calculation**:
```
Pitch = 48°
Flight_Path_Angle = atan2(0.96 m/s, 28.18 m/s) ≈ 2°
Real AOA = 48° - 2° = 46°  ← Way beyond stall!
Clamped AOA = 15° ← Used for lift/drag calculations
```

**Why it exists**: Comment says "LIMIT AOA to prevent unrealistic values and drag explosion"

**Status**: ⚠️ Not fixed - clamping is masking deeper issues

---

### 3. 🔴 CRITICAL: Incorrect Pitch Moment Model
**File**: `src/airborne/physics/flight_model/simple_6dof.py:404-432`

**Problem 1**: Pitch control uses angular VELOCITY instead of angular ACCELERATION:
```python
pitch_rate_control = 1.0  # rad/s per unit input  ← This is VELOCITY!
pitch_input_moment = inputs.pitch * pitch_rate_control  ← Should be ACCELERATION!
```

In proper flight dynamics:
- Elevator input creates a pitching **moment** (torque)
- Moment / Inertia = angular **acceleration**
- Acceleration integrates to angular velocity
- Velocity integrates to rotation angle

Current code confuses angular velocity with angular acceleration.

**Problem 2**: Stability moment calculation may be incorrect:
```python
stability_coefficient = 0.08  # Cm_alpha
pitch_error = self.state.rotation.x - trimmed_pitch  # 48° - 0° = 48°
stability_moment = -stability_coefficient * pitch_error * dynamic_pressure_factor
# = -0.08 * 48° * 0.6 ≈ -2.3 rad/s
```

At 48° pitch error, this creates a strong nose-down "moment" of -2.3 rad/s.

But with the angular velocity integration fix, this -2.3 rad/s is now being **integrated** as if it were an acceleration, which compounds the problem.

**Status**: 🔴 Critical issue - pitch control fundamentally broken

---

### 4. 🔴 CRITICAL: Linear Lift Coefficient Model (No Stall)
**File**: `src/airborne/physics/flight_model/simple_6dof.py:271-272`

**Problem**: Lift uses simple linear model that doesn't account for stall:
```python
cl = self.lift_coefficient_slope * (angle_of_attack * RADIANS_TO_DEGREES)
lift_magnitude = q * self.wing_area * cl
```

**Real aerodynamics** (C172):
- **0° to ~15° AOA**: CL increases linearly (~0.1 per degree)
- **~16-18° AOA**: Stall begins, CL peaks at ~1.5-1.6
- **>18° AOA**: CL drops dramatically (stall), high drag

**Current model**:
- CL just keeps increasing linearly with AOA
- No stall behavior
- With clamping at 15°, CL = 0.1 * 15 = 1.5 (right at stall CL)
- Without clamping, CL would be 0.1 * 46 = 4.6 (physically impossible!)

**Why aircraft climbs**:
- At AOA=15° (clamped), CL ≈ 1.5
- Lift = 0.5 * ρ * V² * S * CL = 11,829 N
- Weight = 11,880 N
- Lift ≈ Weight, so aircraft maintains altitude/climbs slowly

**Status**: 🔴 Critical - no stall modeling

---

### 5. 🟡 MODERATE: Pitch Reaches Impossible Equilibrium
**Observed**: Pitch stabilizes at 48° with neutral elevator

**Why this happens**:
1. Pitch starts climbing due to some initial disturbance or trim setting
2. As pitch increases, stability moment creates nose-down tendency
3. With broken angular velocity integration (now fixed), pitch couldn't respond properly
4. After the integration fix, pitch control model is still wrong (velocity vs acceleration)
5. System reaches equilibrium where:
   - Elevator input (≈0) + Trim (≈0) + Stability moment (large negative) = 0
   - But these values are in wrong units (mixing velocity and acceleration)

**Expected behavior**:
- With neutral elevator and no trim, aircraft should return to ~3-5° pitch
- Stability should prevent pitch from exceeding ~30° even with full back stick

**Status**: 🟡 Secondary effect of pitch control bug

---

### 6. 🟡 MODERATE: Airspeed Stuck at 55 Knots
**Observed**: Airspeed constant at 54.8 knots

**Analysis**:
```
Thrust = 1840 N
Drag = 1366 N
Net horizontal force = 1840 - 1366 = 474 N (should accelerate)
```

**Why not accelerating**:
1. Pitch at 48° means thrust vector points mostly upward:
   ```
   Thrust_horizontal = 1840 * cos(48°) ≈ 1230 N
   Thrust_vertical = 1840 * sin(48°) ≈ 1368 N
   ```
2. Most thrust is fighting gravity, not accelerating forward
3. Aircraft in equilibrium: Thrust_horizontal ≈ Drag

**Expected behavior**:
- At normal cruise pitch (3-5°), thrust would accelerate aircraft
- Aircraft should reach 100+ knots in level flight

**Status**: 🟡 Secondary effect of stuck pitch

---

## Interaction of Issues

The bugs create a cascading failure:

1. **Angular velocity integration bug** (fixed) caused initial pitch divergence
2. **Pitch control model** confuses velocity and acceleration, preventing proper recovery
3. **Pitch stuck at 48°** creates impossible flight regime:
   - Real AOA = 46° (way beyond stall)
   - AOA clamped to 15° for lift calculation
4. **No stall model** means aircraft generates unrealistic lift at high AOA
5. **Lift ≈ Weight** at 55 kts with clamped AOA, creating slow climb
6. **Thrust mostly vertical** at 48° pitch prevents acceleration
7. **Aircraft stuck** in impossible equilibrium

---

## Recommended Fixes (Priority Order)

### Priority 1: Fix Pitch Control Model (CRITICAL)

**File**: `src/airborne/physics/flight_model/simple_6dof.py:404-432`

The pitch control model needs to be rewritten to use proper moment-based physics:

```python
# === PITCH CONTROL (Proper moment-based physics) ===

# Elevator creates pitching moment proportional to dynamic pressure and deflection
# M = q * S * c * Cm_delta_e * delta_e
# where:
#   q = dynamic pressure (0.5 * rho * V^2)
#   S = wing area
#   c = mean aerodynamic chord
#   Cm_delta_e = elevator effectiveness coefficient
#   delta_e = elevator deflection

q = 0.5 * AIR_DENSITY_SEA_LEVEL * airspeed**2
chord = 1.5  # meters (C172 MAC)

# Elevator authority (Cm_delta_e for C172)
elevator_authority = 0.02  # Cm per degree of elevator

# Pitching moment from elevator (N⋅m)
elevator_moment = q * self.wing_area * chord * elevator_authority * inputs.pitch

# Pitching moment from trim
trim_authority = 0.005  # Smaller than elevator
trim_moment = q * self.wing_area * chord * trim_authority * self.state.pitch_trim

# Aerodynamic stability (Cm_alpha)
# Creates nose-down moment when AOA is above trimmed AOA
aoa = self._calculate_angle_of_attack()  # radians
trimmed_aoa = 0.05  # ~3° trimmed AOA in cruise
stability_authority = -0.10  # Cm_alpha (negative = stable)
stability_moment = q * self.wing_area * chord * stability_authority * (aoa - trimmed_aoa)

# Total pitching moment (N⋅m)
total_pitch_moment = elevator_moment + trim_moment + stability_moment

# Angular acceleration = Moment / Inertia
pitch_inertia = 1500.0  # kg⋅m² (C172 pitch moment of inertia)
pitch_angular_acceleration = total_pitch_moment / pitch_inertia  # rad/s²

# Similarly for roll and yaw...
```

**Key changes**:
- Use moment-based physics, not arbitrary velocity targets
- Proper dynamic pressure scaling
- Correct units (acceleration, not velocity)
- Realistic coefficients for C172

---

### Priority 2: Implement Proper Stall Model (CRITICAL)

**File**: `src/airborne/physics/flight_model/simple_6dof.py:260-280`

Replace linear lift model with realistic stall curve:

```python
def _calculate_lift_coefficient(self, angle_of_attack_rad: float) -> float:
    """Calculate lift coefficient with stall behavior.

    Args:
        angle_of_attack_rad: Angle of attack in radians

    Returns:
        Lift coefficient (dimensionless)
    """
    aoa_deg = angle_of_attack_rad * RADIANS_TO_DEGREES

    # Cessna 172 lift curve data
    CL_0 = 0.2  # Zero-lift offset
    CL_alpha = 0.1  # Lift curve slope (per degree)
    stall_aoa = 16.0  # degrees
    max_cl = 1.6  # Maximum CL at stall

    if aoa_deg < stall_aoa:
        # Linear region before stall
        cl = CL_0 + CL_alpha * aoa_deg
        cl = min(cl, max_cl)  # Cap at max CL
    else:
        # Post-stall: CL drops dramatically
        # Use cosine model for smooth stall
        stall_excess = aoa_deg - stall_aoa
        cl = max_cl * math.exp(-0.05 * stall_excess)  # Exponential decay
        cl = max(cl, 0.3)  # Minimum post-stall CL

    # Handle negative AOA (negative CL)
    if aoa_deg < -5.0:
        cl = CL_0 + CL_alpha * aoa_deg

    return cl
```

**Then remove AOA clamping**:
```python
# Remove these lines:
# MAX_AOA_DEG = 15.0
# MAX_AOA = MAX_AOA_DEG * DEGREES_TO_RADIANS
# angle_of_attack = max(-MAX_AOA, min(MAX_AOA, angle_of_attack))

# Use proper stall model instead:
cl = self._calculate_lift_coefficient(angle_of_attack)
lift_magnitude = q * self.wing_area * cl
```

**Impact**:
- Aircraft will stall realistically at ~16° AOA
- Lift drops in post-stall, causing nose-down pitch moment
- Cannot maintain 48° pitch - will stall and recover

---

### Priority 3: Add Proper Drag Model (HIGH)

**File**: `src/airborne/physics/flight_model/simple_6dof.py:310-340`

Current drag model needs stall-induced drag:

```python
def _calculate_drag_coefficient(self, cl: float, angle_of_attack_rad: float) -> float:
    """Calculate total drag coefficient.

    Args:
        cl: Lift coefficient
        angle_of_attack_rad: Angle of attack in radians

    Returns:
        Drag coefficient (dimensionless)
    """
    # Parasite drag (CD_0)
    cd_parasite = 0.027  # C172 clean config

    # Induced drag: CD_i = CL² / (π * e * AR)
    aspect_ratio = 7.4  # C172
    oswald_efficiency = 0.7
    cd_induced = (cl**2) / (math.pi * oswald_efficiency * aspect_ratio)

    # Stall drag: Additional drag in stall
    aoa_deg = angle_of_attack_rad * RADIANS_TO_DEGREES
    if aoa_deg > 16.0:
        # Drag increases dramatically in stall
        stall_excess = aoa_deg - 16.0
        cd_stall = 0.5 * (1.0 - math.exp(-0.1 * stall_excess))
    else:
        cd_stall = 0.0

    return cd_parasite + cd_induced + cd_stall
```

---

### Priority 4: Test and Validate (HIGH)

After fixes, validate with these scenarios:

#### Test 1: Takeoff
```
Initial: Ground, 0 kts, pitch 0°
Throttle: Full (100%)
Expected:
  - Accelerate to 60 kts in ~20 seconds
  - Rotate to 10-12° pitch at 60 kts
  - Lift off smoothly
  - Climb at 70-80 kts
```

#### Test 2: Level Flight
```
Initial: 3000 ft, 100 kts, pitch 3°
Throttle: 65%
Expected:
  - Maintain altitude ±50 ft
  - Airspeed stable 95-105 kts
  - Pitch stable 2-5°
```

#### Test 3: Stall Recovery
```
Initial: 5000 ft, reduce throttle, pull back on yoke
Expected:
  - Airspeed decreases
  - Stall warning at ~55 kts
  - Stall at ~50 kts, AOA ~16-18°
  - Nose drops, aircraft pitches down
  - Airspeed increases, lift recovers
  - Return to normal flight
```

#### Test 4: Pitch Control
```
Initial: Level flight, 100 kts
Action: Push yoke forward (elevator -0.5)
Expected:
  - Pitch decreases 2-3° per second
  - Aircraft descends
  - Airspeed increases

Action: Pull yoke back (elevator +0.5)
Expected:
  - Pitch increases 2-3° per second
  - Aircraft climbs
  - Airspeed decreases (if no throttle added)
```

---

## Implementation Plan

### Step 1: Fix Pitch Control (Essential)
1. Rewrite pitch control to use moment-based physics
2. Add proper moment of inertia
3. Scale with dynamic pressure
4. Use realistic coefficients
5. Test with neutral stick - should maintain ~5° pitch in cruise

### Step 2: Implement Stall Model (Essential)
1. Add `_calculate_lift_coefficient()` method
2. Implement pre-stall and post-stall regions
3. Remove AOA clamping
4. Test: Aircraft should stall at 16° AOA, not pitch angle

### Step 3: Add Stall Drag (Important)
1. Add `_calculate_drag_coefficient()` method
2. Include stall-induced drag
3. Test: High drag in stall helps nose drop

### Step 4: Comprehensive Testing (Critical)
1. Unit tests for lift curve (stall behavior)
2. Unit tests for pitch moments
3. Integration test: takeoff to landing
4. Manual testing: verify user observations fixed

---

## Expected Results After Fixes

✅ **Pitch control works**:
- Forward yoke → nose down → descend
- Back yoke → nose up → climb (until stall)
- Neutral yoke → maintain pitch

✅ **Stall behavior realistic**:
- Stall at 16-18° AOA (not pitch!)
- Nose drops in stall
- Can recover by releasing back pressure

✅ **Airspeed control works**:
- More throttle → faster
- Less throttle → slower
- Can reach 100+ kts in level flight

✅ **Normal flight possible**:
- Cruise at 100 kts, 3-5° pitch
- Climb at 70 kts, 10-12° pitch
- Descend with forward yoke

---

## Additional Notes

### Why These Bugs Weren't Caught Earlier

1. **Angular velocity integration bug** was subtle - code "worked" but gave wrong results
2. **Pitch control model** has wrong physics but produced some pitch response
3. **AOA clamping** masked the stall issue by limiting lift/drag calculations
4. **Linear lift model** worked okay for small AOA, only breaks in extremes
5. **Cascading failures** made it hard to identify individual bugs

### Related Issues to Monitor

1. **Throttle to thrust**: May need adjustment after pitch control fix
2. **Ground physics**: Should limit pitch rotation on ground
3. **Trim system**: Needs validation after pitch fix
4. **Flight instructor**: Should warn based on AOA, not just airspeed

---

## References

- **Telemetry**: `/tmp/airborne_telemetry_20251030_170024.db`
- **Analysis script**: `scripts/analyze_physics_issue.py`
- **Previous fixes**: `AOA_FIX_SUMMARY.md`, `ACCELERATION_FIX_COMPLETE.md`
- **C172 Performance**: POH (Pilot's Operating Handbook)
- **Aerodynamics**: Anderson, "Introduction to Flight"

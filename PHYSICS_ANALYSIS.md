# Physics and Flight Model Analysis

**Date**: 2025-10-30
**Issue**: Stall warnings with neutral pitch, random climbing/descending during takeoff

---

## Summary of Problems

Based on telemetry analysis from `/tmp/airborne_telemetry_20251030_164032.db`:

### 1. **Critical: Angle of Attack Equals Pitch Angle** ⚠️

**Observation:**
```
Pitch: 28.15° → AOA: 28.13°
Pitch: 28.13° → AOA: 28.11°
Pitch: 28.05° → AOA: 28.03°
```

**Root Cause:**
In `src/airborne/physics/flight_model/simple_6dof.py` line 234:
```python
angle_of_attack = self.state.get_pitch()  # radians
```

**This is WRONG!** AOA should be calculated from velocity vector relative to aircraft body axes, NOT just pitch angle.

**Correct Formula:**
```python
# AOA = arctan(velocity_z / velocity_x) in body frame
# Or: AOA = pitch - flight_path_angle
```

**Impact:**
- Incorrect lift calculations
- Wrong stall detection
- Unrealistic flight dynamics
- Aircraft behaves incorrectly in climbs/descents

---

### 2. **High Pitch with Neutral Elevator** ⚠️

**Observation:**
- Pitch angle: 27-28° (very high for level flight)
- Elevator input: 0.046 (essentially neutral)
- Airspeed: 44-46 knots (dangerously low)

**This indicates:**
1. Elevator control has insufficient authority
2. Or pitch moment calculations are wrong
3. Or lift creates excessive pitching moment
4. Or there's an integration issue in angular dynamics

**Expected Behavior:**
- Neutral elevator at 45 knots should result in pitch ~0-5° (depending on trim)
- Current 28° pitch at neutral elevator is physically impossible

---

### 3. **Low Airspeed (Near Stall)** ⚠️

**Observation:**
- Airspeed: 44-46 knots
- Stall speed (Vs0): ~55 knots
- Current airspeed is **20% below stall speed**

**With 28° pitch, the aircraft should:**
- Either stall immediately (lose lift)
- Or climb rapidly if engine has sufficient power

**Current behavior is physically incorrect** - you can't maintain 28° pitch at 45 knots without stalling.

---

## Telemetry Data

### Last 50 Frames (All showing same issue):

| Time | IAS(kt) | Pitch(°) | Elevator | AOA(°) | Lift(N) | Drag(N) | Status |
|------|---------|----------|----------|--------|---------|---------|--------|
| 208.5 | 46.4 | 28.15 | 0.046 | 28.13 | 8449 | 2936 | STALL CONDITION |
| 208.5 | 46.4 | 28.13 | 0.046 | 28.11 | 8438 | 2929 | STALL CONDITION |
| 208.5 | 46.3 | 28.11 | 0.046 | 28.10 | 8427 | 2922 | STALL CONDITION |

**All 50 frames are identical** - aircraft stuck in impossible flight regime.

---

## Root Causes

### 1. AOA Calculation Bug (Primary Issue)

**File:** `src/airborne/physics/flight_model/simple_6dof.py`
**Lines:** 234, 286

```python
# CURRENT (WRONG):
angle_of_attack = self.state.get_pitch()  # Just uses pitch angle

# CORRECT APPROACH:
# Calculate flight path angle from velocity
flight_path_angle = math.atan2(velocity.y, velocity_horizontal)
angle_of_attack = pitch - flight_path_angle

# Or calculate from body-frame velocity:
# v_body = rotate_vector_to_body_frame(velocity, rotation)
# angle_of_attack = math.atan2(v_body.y, v_body.x)
```

**Why this matters:**
- AOA determines lift and drag coefficients
- Wrong AOA = wrong forces = wrong flight dynamics
- A Cessna 172 stalls at AOA ~16-18°, not at pitch 16-18°!

---

### 2. Pitch Control Issue (Secondary)

The flight model may have:
- Insufficient pitching moment from elevator
- Wrong moment arm or coefficient
- Integration timestep issues
- Missing pitch damping

**Needs investigation in:**
- Elevator authority calculations
- Pitching moment application
- Angular dynamics integration

---

### 3. Flight Instructor Plugin Limitations

**Current Implementation:**
`src/airborne/plugins/training/flight_instructor_plugin.py` lines 267-271

```python
# Check for dangerously low airspeed
if self.airspeed < self.stall_warning_speed + 10.0:
    self._speak("MSG_INSTRUCTOR_AIRSPEED_LOW", MessagePriority.HIGH)
```

**Problem:** Uses airspeed only, not AOA!

**Should be:**
```python
# Proper stall detection uses AOA
if angle_of_attack_deg > 16.0:  # Cessna 172 stall AOA
    self._speak("MSG_INSTRUCTOR_STALL_WARNING", MessagePriority.CRITICAL)
```

---

## Recommended Fixes (Priority Order)

### **Priority 1: Fix AOA Calculation** 🔥

This is the root cause affecting all flight dynamics.

**File:** `src/airborne/physics/flight_model/simple_6dof.py`

**Changes needed:**
1. Calculate flight path angle from velocity vector
2. Compute AOA = pitch - flight_path_angle
3. Test with realistic scenarios

**Implementation:**
```python
def calculate_angle_of_attack(self, velocity: Vector3, pitch: float) -> float:
    """Calculate angle of attack from velocity and pitch.

    Args:
        velocity: Velocity vector in world frame (m/s)
        pitch: Pitch angle in radians

    Returns:
        Angle of attack in radians
    """
    # Calculate flight path angle (gamma)
    velocity_horizontal = math.sqrt(velocity.x**2 + velocity.z**2)

    if velocity_horizontal < 0.1:  # Avoid division by zero
        return pitch  # At very low speed, AOA ≈ pitch

    flight_path_angle = math.atan2(velocity.y, velocity_horizontal)

    # AOA = pitch - flight path angle
    angle_of_attack = pitch - flight_path_angle

    return angle_of_attack
```

**Testing:**
- Level flight: AOA should be ~2-4°
- Climbing: AOA increases
- Descending: AOA decreases
- Should NOT equal pitch angle!

---

### **Priority 2: Fix Pitch Control**

**Investigate:**
1. Elevator effectiveness (moment arm, coefficient)
2. Pitch damping coefficient
3. Integration timestep (may need smaller dt)
4. Initial conditions (trim state)

**File:** `src/airborne/physics/flight_model/simple_6dof.py`

**Check:**
- Pitching moment from elevator: `M = q * S * c * Cm_delta_e * delta_e`
- Moment arm and coefficients realistic?
- Angular acceleration: `alpha = M / I_yy`
- Integration: `omega += alpha * dt`

---

### **Priority 3: Update Flight Instructor**

**File:** `src/airborne/plugins/training/flight_instructor_plugin.py`

**Add AOA-based stall detection:**
```python
def _monitor_stall_warning(self) -> None:
    """Monitor for stall conditions using AOA."""
    if self.stall_feedback_timer > 0:
        return

    # Get AOA from physics state
    angle_of_attack = self.physics_state.get("angle_of_attack_deg", 0.0)

    # Cessna 172 stalls at ~16-18° AOA
    stall_aoa = 16.0
    warning_aoa = 14.0

    if angle_of_attack > stall_aoa:
        self._speak("MSG_INSTRUCTOR_STALL_WARNING", MessagePriority.CRITICAL)
        self.stall_feedback_timer = self.feedback_cooldown
    elif angle_of_attack > warning_aoa:
        self._speak("MSG_INSTRUCTOR_AOA_HIGH", MessagePriority.HIGH)
        self.stall_feedback_timer = self.feedback_cooldown
```

---

## Expected Results After Fixes

### Normal Flight at 70 knots, level:
```
Pitch:     3-5°
AOA:       2-4°
Airspeed:  70 kts
Elevator:  Slight forward trim (~-0.05)
```

### Climb at 75 knots, 8° pitch:
```
Pitch:     8°
AOA:       4-6° (less than pitch due to climb angle)
Airspeed:  75 kts
Elevator:  Slight aft trim (~+0.03)
```

### Current (BROKEN):
```
Pitch:     28° ← WAY TOO HIGH
AOA:       28° ← WRONG (should be different from pitch)
Airspeed:  46 kts ← STALLED
Elevator:  0.046 ← NEUTRAL (should control pitch!)
```

---

## Testing Plan

After implementing fixes:

1. **Ground Test:**
   - Start engine, throttle to idle
   - Check pitch stays ~0° on ground
   - Verify elevator moves pitch up/down

2. **Takeoff Test:**
   - Full throttle, release parking brake
   - At 60 knots, gentle back pressure (elevator ~+0.2)
   - Should rotate to 10-12° pitch
   - Should lift off smoothly
   - Check AOA is 2-4° less than pitch (due to climb angle)

3. **Level Flight Test:**
   - Reduce throttle to cruise power
   - Trim for level flight at 100 knots
   - Pitch should be ~3-5°
   - AOA should be ~2-4°
   - Elevator should be near neutral with trim

4. **Stall Test:**
   - Reduce power to idle
   - Slowly increase pitch
   - Should stall around 16-18° AOA (not pitch!)
   - Instructor should warn before stall
   - Aircraft should pitch down and recover

---

## Files to Modify

1. **`src/airborne/physics/flight_model/simple_6dof.py`** (PRIMARY)
   - Fix AOA calculation (lines 234, 286, 305)
   - Add proper flight path angle calculation
   - Test elevator authority

2. **`src/airborne/plugins/training/flight_instructor_plugin.py`** (SECONDARY)
   - Add AOA-based stall detection
   - Update thresholds for realistic values

3. **`config/aircraft/cessna172.yaml`** (IF NEEDED)
   - May need to adjust elevator effectiveness
   - May need to adjust pitch damping

---

## Additional Notes

### Cessna 172 Reference Values

| Parameter | Value | Notes |
|-----------|-------|-------|
| Stall Speed (clean) | 47-50 KIAS | Vs1 |
| Stall Speed (full flaps) | 40-44 KIAS | Vs0 |
| Stall AOA | 16-18° | Critical AOA |
| Cruise Speed | 100-120 KIAS | Normal cruise |
| Cruise AOA | 2-4° | Level flight |
| Climb Speed | 70-80 KIAS | Vy = 74 KIAS |
| Climb AOA | 4-8° | Typical climb |

### Current Telemetry Shows:
- Airspeed: 46 kts (BELOW Vs0!)
- AOA: 28° (160% above stall AOA!)
- This is physically impossible to maintain

---

## Conclusion

The primary issue is **incorrect AOA calculation** in the flight model. It uses pitch angle directly instead of calculating AOA from velocity vectors. This cascades into:

1. Wrong lift/drag forces
2. Unrealistic flight dynamics
3. Incorrect stall behavior
4. Pitch control problems

**Fix the AOA calculation first**, then reassess pitch control and instructor warnings.

---

**Analysis Script:** `scripts/analyze_physics_issue.py`
**Telemetry Database:** `/tmp/airborne_telemetry_20251030_164032.db`

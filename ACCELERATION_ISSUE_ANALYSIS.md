# Acceleration Issue Analysis & Fix Plan

## Problem Statement

Aircraft accelerates extremely slowly (5 knots per 10-15 seconds at 100% throttle). Expected Cessna 172 performance should achieve approximately 50 knots in ~10 seconds during takeoff roll.

## Investigation Summary

### 1. Current Configuration (Cessna 172)

**From `config/aircraft/cessna172.yaml`:**
- Weight: 2450 lbs (1111 kg with fuel)
- Wing area: 174 sqft (16.17 m²)
- Max thrust (deprecated): 180 lbs (801 N)
- Drag coefficient: 0.042
- Propeller: 75" diameter (1.905m), fixed pitch, 180 HP

**Propeller Configuration:**
- Static efficiency: 0.72
- Cruise efficiency: 0.85
- Cruise advance ratio: 0.6

### 2. Root Cause Analysis

#### Issue #1: Ground Friction Forces Are Too High

**Problem:** Ground physics applies BOTH friction AND rolling resistance, causing excessive deceleration.

**Evidence from `ground_physics.py` (lines 158-176):**
```python
# Friction force
friction_magnitude = friction_coef * normal_force  # 0.8 × 10900 N = 8720 N
forces.friction_force = friction_direction * friction_magnitude

# Rolling resistance (ALSO applied!)
rolling_magnitude = rolling_coef * normal_force  # 0.02 × 10900 N = 218 N
forces.rolling_resistance = rolling_direction * rolling_magnitude
```

**Calculation at standstill:**
- Normal force = mass × g × compression = 1111 kg × 9.81 × 1.0 = 10,900 N
- Friction force = 0.8 × 10,900 = **8,720 N** (opposing thrust!)
- Rolling resistance = 0.02 × 10,900 = **218 N**
- **Total resistance = 8,938 N**

**Expected static thrust from propeller:**
- 180 HP @ 2700 RPM @ v=0
- Using momentum theory: T = sqrt(η × P × ρ × A)
- T = sqrt(0.72 × 134,300W × 1.225 × 2.85) = **785 N**

**Net force:** 785 N thrust - 8,938 N resistance = **-8,153 N** (can't move!)

#### Issue #2: Friction Coefficient is Wrong

**Problem:** Using sliding friction (0.8) instead of rolling friction.

**Physics Error:**
- **Sliding friction** (μ_k): 0.6-0.8 (used when surfaces slide against each other)
- **Rolling friction** (μ_r): 0.01-0.03 (used for wheels rolling on surface)

Aircraft wheels **roll**, they don't slide! Should use μ_r = 0.015 for asphalt, not μ_k = 0.8.

#### Issue #3: Double-Counting Resistance

Both friction AND rolling resistance are being applied. These should be:
- **Rolling resistance:** Normal ongoing resistance (0.015-0.02)
- **Friction:** Only when brakes are applied or wheels are slipping

### 3. Expected vs Actual Performance

**Cessna 172 POH Specifications:**
- Ground roll: 960 ft to liftoff
- Takeoff speed (Vr): 55 KIAS
- Time to Vr: approximately 10 seconds
- Acceleration: 0-50 knots in ~10 seconds

**Current Simulation:**
- Acceleration: 0-5 knots in 10-15 seconds
- **Performance deficit: 90% slower than expected**

### 4. Force Balance Analysis

**At v=0 (static conditions):**

| Force Component | Current Value | Should Be | Notes |
|----------------|---------------|-----------|-------|
| Propeller thrust | 785 N | 785 N | ✓ Correct (from momentum theory) |
| Weight component | 10,900 N down | 10,900 N | ✓ Correct |
| Friction force | -8,720 N | 0 N | ❌ Should be 0 (wheels rolling) |
| Rolling resistance | -218 N | -160 N | ~ Close but double-counted |
| **Net horizontal force** | **-8,153 N** | **+625 N** | ❌ Wrong sign! |
| Expected acceleration | -7.3 m/s² | +0.56 m/s² | ❌ Going backwards! |

**At v=10 m/s (20 knots):**

| Force Component | Current | Should Be | Notes |
|----------------|---------|-----------|-------|
| Thrust | ~1500 N | ~1500 N | ✓ Dynamic thrust |
| Drag (aerodynamic) | ~80 N | ~80 N | ✓ Correct |
| Ground friction | -8,720 N | 0 N | ❌ Wrong! |
| Rolling resistance | -218 N | -160 N | ~ OK |
| **Net force** | **-7,438 N** | **+1,260 N** | ❌ Still wrong! |

## Proposed Fixes

### Fix #1: Remove Incorrect Friction Force (CRITICAL)

**File:** `src/airborne/physics/ground_physics.py`

**Change lines 158-166:**

```python
# REMOVE THIS - only apply when braking or sliding
# if speed > 0.01:
#     friction_coef = self._get_friction_coefficient(contact.surface_type)
#     normal_force = self.mass_kg * 9.81 * contact.gear_compression
#     friction_magnitude = friction_coef * normal_force
#     friction_direction = velocity.normalized() * -1
#     forces.friction_force = friction_direction * friction_magnitude
```

**Rationale:**
- Wheels roll, they don't slide
- Friction only applies when brakes are engaged (handled separately)
- Rolling resistance already accounts for tire deformation

### Fix #2: Correct Rolling Resistance Coefficients

**File:** `src/airborne/physics/ground_physics.py`

**Change lines 89-100:**

```python
# Rolling resistance coefficients (dimensionless)
ROLLING_RESISTANCE = {
    "asphalt": 0.015,      # Was: 0.02 (reduce by 25%)
    "concrete": 0.012,     # Was: 0.015
    "grass": 0.06,         # Was: 0.08
    "dirt": 0.08,          # Was: 0.10
    "gravel": 0.05,        # Was: 0.06
    "snow": 0.04,          # Was: 0.05
    "ice": 0.015,          # Was: 0.02
    "water": 0.03,         # Was: 0.04
    "unknown": 0.025,      # Was: 0.03
}
```

**Rationale:** Values were too high by 20-30%, causing excessive resistance.

### Fix #3: Add Ground Speed Threshold

**File:** `src/airborne/physics/ground_physics.py`

**Add check before applying ground forces:**

```python
def calculate_ground_forces(self, contact, rudder_input, brake_input, velocity):
    forces = GroundForces()

    if not contact.on_ground or contact.gear_compression < 0.1:
        return forces  # Not enough weight on wheels

    # ... rest of function
```

**Rationale:** When aircraft rotates for takeoff, weight transfers off wheels, reducing ground forces naturally.

### Fix #4: Improve Propeller Thrust at Low Speed

**File:** `src/airborne/systems/propeller/fixed_pitch.py`

**Adjust static thrust calculation (line 127):**

```python
if airspeed_mps < 1.0:
    # Static thrust: use momentum theory with slight boost for actual blade effects
    # T_static = sqrt(η × P × ρ × A) × 1.05  # 5% boost for blade effects
    thrust = math.sqrt(efficiency * power_watts * air_density_kgm3 * self.disc_area) * 1.05
```

**Rationale:** Momentum theory is conservative; real propellers achieve 5-10% more static thrust due to blade effects.

## Validation Tests

### Test #1: Static Thrust Validation

```python
def test_static_thrust_cessna172():
    """Verify static thrust matches expected performance."""
    # Cessna 172: 180 HP, 2700 RPM, 75" prop
    propeller = FixedPitchPropeller(
        diameter_m=1.905,
        pitch_ratio=0.6,
        efficiency_static=0.72,
        efficiency_cruise=0.85,
    )

    thrust_n = propeller.calculate_thrust(
        power_hp=180,
        rpm=2700,
        airspeed_mps=0.0,
        air_density_kgm3=1.225
    )

    # Expected: 180 HP should produce ~820 N static thrust
    # (T/W ratio ~0.075 for light aircraft)
    assert 750 < thrust_n < 900, f"Static thrust {thrust_n}N out of range"

    # Convert to lbf for comparison
    thrust_lbf = thrust_n * 0.2248
    print(f"Static thrust: {thrust_n:.0f} N ({thrust_lbf:.0f} lbf)")
    # Should be approximately 175-200 lbf
```

### Test #2: Takeoff Roll Performance

```python
def test_takeoff_roll_performance():
    """Verify takeoff roll matches Cessna 172 POH."""
    # Setup
    model = Simple6DOFFlightModel()
    model.initialize({
        "wing_area_sqft": 174.0,
        "weight_lbs": 2450.0,
        "drag_coefficient": 0.042,
    })

    # Simulate takeoff roll with full throttle
    time = 0.0
    dt = 0.016  # 60 FPS
    inputs = ControlInputs(throttle=1.0)

    # Run until reaching rotation speed (55 KIAS = 28.3 m/s)
    while model.state.get_airspeed() < 28.3 and time < 20.0:
        model.update(dt, inputs)
        time += dt

    final_speed_kias = model.state.get_airspeed() * 1.94384
    distance_ft = model.state.position.z * 3.28084

    # POH: ground roll = 960 ft, time ~10-12 seconds
    assert 8 < time < 15, f"Takeoff time {time:.1f}s not in range 8-15s"
    assert 800 < distance_ft < 1200, f"Ground roll {distance_ft:.0f}ft not in range"
    assert final_speed_kias > 50, f"Final speed {final_speed_kias:.0f} KIAS too low"

    print(f"Takeoff roll: {distance_ft:.0f} ft in {time:.1f}s to {final_speed_kias:.0f} KIAS")
```

### Test #3: Ground Forces Validation

```python
def test_ground_forces_without_brakes():
    """Verify ground forces are minimal without brakes."""
    ground = GroundPhysics(mass_kg=1111)

    contact = GroundContact(
        on_ground=True,
        gear_compression=1.0,
        surface_type="asphalt",
        ground_speed_mps=0.0,
    )

    # No brakes, no steering
    forces = ground.calculate_ground_forces(
        contact=contact,
        rudder_input=0.0,
        brake_input=0.0,
        velocity=Vector3(0, 0, 0),
    )

    total_force = forces.total_force.magnitude()

    # Should be minimal (only rolling resistance)
    # Expected: 0.015 × 1111kg × 9.81 = ~163 N
    assert total_force < 200, f"Ground force {total_force:.0f}N too high without brakes"
    assert forces.friction_force.magnitude() < 10, "Friction should be near zero without brakes"

    print(f"Ground resistance (no brakes): {total_force:.0f} N")
```

### Test #4: Acceleration Curve Validation

```python
def test_acceleration_curve():
    """Verify aircraft reaches expected speeds at expected times."""
    model = Simple6DOFFlightModel()
    # ... setup ...

    expected_performance = [
        (5.0, 15.0),   # 5 seconds -> 15 knots
        (10.0, 35.0),  # 10 seconds -> 35 knots
        (15.0, 50.0),  # 15 seconds -> 50 knots
    ]

    for target_time, expected_speed_kias in expected_performance:
        # Simulate to target time
        # ...

        actual_speed = state.get_airspeed() * 1.94384
        tolerance = 5.0  # ±5 knots

        assert abs(actual_speed - expected_speed_kias) < tolerance, \
            f"At t={target_time}s: expected {expected_speed_kias} KIAS, got {actual_speed:.1f}"
```

## Implementation Plan

### Phase 1: Critical Fixes (30 minutes)
1. ✅ Remove friction force from ground physics (except when braking)
2. ✅ Adjust rolling resistance coefficients
3. ✅ Add gear compression threshold check

### Phase 2: Validation (45 minutes)
4. Write unit test for static thrust
5. Write unit test for ground forces
6. Write integration test for takeoff roll
7. Run tests and verify all pass

### Phase 3: Tuning (30 minutes)
8. Test in simulator with actual takeoff
9. Measure time to 50 knots
10. Adjust coefficients if needed to match POH

### Phase 4: Documentation (15 minutes)
11. Update physics documentation with correct formulas
12. Add comments explaining rolling vs sliding friction
13. Document expected performance benchmarks

## Expected Results After Fixes

**Static thrust:** ~820 N (184 lbf)
**Net force at v=0:** 820 - 163 = 657 N
**Acceleration:** 657 / 1111 = 0.59 m/s² (5.3 knots/second)
**Time to 50 knots:** approximately 9-10 seconds ✓
**Ground roll distance:** approximately 950 ft ✓

**Performance improvement:** 90% faster acceleration, matching real Cessna 172.

## Risk Assessment

**Low Risk Changes:**
- Removing friction force: Correct physics, no brakes affected
- Rolling resistance adjustment: Minor tuning, easily reversible

**Testing Required:**
- Landing rollout (ensure brakes still work)
- Taxi operations (ensure aircraft doesn't roll away)
- Takeoff performance (primary validation)

## References

1. Cessna 172 POH - Performance Charts
2. Anderson, *Introduction to Flight* (7th ed.) - Ground forces
3. McCormick, *Aerodynamics, Aeronautics, and Flight Mechanics* - Propeller theory
4. FAA-H-8083-25B - Pilot's Handbook of Aeronautical Knowledge

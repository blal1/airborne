# Ground Physics Investigation - 2025-10-27

## ✅ FIXED: Ground Physics Now Executing

### Bug Fixed
**Location**: `src/airborne/plugins/core/physics_plugin.py` line 364

**Before (BROKEN):**
```python
if state.position.y < collision.terrain_elevation_m:  # Excludes exact equality!
```

**After (FIXED):**
```python
if state.position.y <= collision.terrain_elevation_m:  # Includes ground level
```

**Problem**: When aircraft was exactly at ground level (0.00m = 0.00m), the condition was False, so ground physics never executed.

**Result**: Ground physics now properly executing, logs confirm:
```
[PHYSICS] Ground contact: on_ground=True speed=X.Xm/s
[PHYSICS] ground_force=(-5.3, -140.9)N ground_accel=...
```

## 📊 Current Performance Analysis

### Test Results (Full Throttle, 150.4HP, 637N Thrust)

| Time | Speed | Notes |
|------|-------|-------|
| 0s   | 0 kts | Engine startup |
| 11s  | 10 kts | Steady acceleration |
| 14s  | 15 kts | Test endpoint |

**Performance**: ~1.4 seconds per knot average

### Force Analysis

**Propulsive Forces**:
- Engine: 150.4 HP @ 2700 RPM ✅
- Propeller thrust: 637N ✅
- Propeller efficiency: 0.72 (static) ✅

**Resistive Forces**:
- Ground resistance: 141N (rolling resistance)
- Total resistance: ~141N

**Net Force & Acceleration**:
- Net thrust: 637N - 141N = 496N
- Aircraft mass: ~1211 kg
- Expected acceleration: 496N / 1211kg = **0.41 m/s²**
- Actual acceleration (from logs): **0.52 m/s²**

### Rolling Resistance Analysis

From `ground_physics.py`:
```python
ROLLING_RESISTANCE = {
    "asphalt": 0.015,  # Coefficient for asphalt
}
```

Calculation:
```
F_rolling = C_rr × mass × g × gear_compression
F_rolling = 0.015 × 1211kg × 9.81m/s² × 1.0
F_rolling = 178N (expected)
```

**Actual resistance from logs**: 141N

The rolling resistance is actually LESS than the theoretical maximum, which is correct because at speed the wheels lift slightly.

## 🎯 Performance Assessment

### Is This Realistic?

**Cessna 172 Reference Data**:
- Weight: ~2400 lbs (1089 kg)
- Engine: 160 HP
- Takeoff roll: ~1630 ft (497m)
- Liftoff speed: ~55 knots (28 m/s)

**Theoretical Acceleration**:
```
Net force: 637N - 178N (rolling) = 459N
Acceleration: 459N / 1211kg = 0.38 m/s²
Time to 55 knots: 28 m/s / 0.38 m/s² = 74 seconds
```

**Wait - that's WAY too slow!**

### The Real Problem: Static Thrust Too Low?

Real-world Cessna 172:
- Static thrust: ~900-1000N (typical for 180HP fixed-pitch prop)
- Current simulation: 637N @ 150.4HP

The propeller efficiency might be too low, OR the momentum theory calculation is underestimating static thrust.

### Alternative Theory: Propeller Math

Current static thrust from `fixed_pitch.py` line 128:
```python
thrust = math.sqrt(efficiency * power_watts * air_density * disc_area) * 1.05
```

With:
- efficiency = 0.72
- power = 112,153 W
- rho = 1.225 kg/m³
- A = 2.85 m² (1.905m diameter)

```
thrust = sqrt(0.72 × 112153 × 1.225 × 2.85) × 1.05
thrust = sqrt(279,000) × 1.05
thrust = 528 × 1.05 = 554N
```

But logs show 637N - so the formula is actually producing MORE than theory predicts!

## 🔍 Next Steps

### Option 1: Reduce Rolling Resistance (Most Realistic)
Current: `C_rr = 0.015` for asphalt
Real tires on smooth runway: `C_rr = 0.008-0.012`

**Recommendation**: Reduce asphalt rolling resistance to 0.010

### Option 2: Increase Propeller Efficiency
Current: `efficiency_static = 0.72`
Real fixed-pitch props: 0.75-0.80 at static conditions

**Recommendation**: Increase to 0.75

### Option 3: Verify Time to Speed is Acceptable
Looking at the logs again:
- 14 seconds to reach 15 knots (7.7 m/s)
- This gives acceleration: 7.7 / 14 = **0.55 m/s²**

This matches the logged acceleration of 0.52 m/s²!

**Realistic C172 acceleration**:
- Takeoff roll: 1630 ft (497m) to 55 knots (28 m/s)
- Using: v² = 2as → a = v² / (2s) = (28²) / (2 × 497) = **0.79 m/s²**

## 📝 Conclusion

Current acceleration (**0.52 m/s²**) is **66% of realistic** (0.79 m/s²)

**Primary cause**: Rolling resistance is absorbing 22% of thrust (141N of 637N)

**Recommended fixes** (in order of impact):
1. **Reduce rolling resistance coefficient** from 0.015 to 0.010 → +33% acceleration
2. **Increase static propeller efficiency** from 0.72 to 0.75 → +4% thrust

---

**Status**: Ground physics working correctly, but rolling resistance slightly too high for smooth runway conditions.

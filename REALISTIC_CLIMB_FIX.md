# Realistic Solution: Fix Propeller Thrust at Climb Speeds

## Problem Analysis

You're correct - increasing `static_thrust_multiplier` would make ground acceleration unrealistically strong.

### Current Behavior at Climb Speed (69 kts, J=0.438):

1. **Static thrust correction**: At J=0.438, the multiplier is still active:
   - correction = 4.3 - (4.3 - 1.0) × ((0.438 - 0.05) / (0.6 - 0.05))
   - correction = 4.3 - 3.3 × 0.705 = **2.03×**

2. **Blend factor**: At J=0.438, the thrust formula is blending:
   - blend = 0.05 + (0.438 - 0.20) × (0.90 - 0.05) / (0.7 - 0.20)
   - blend = **0.455** (45.5% dynamic, 54.5% static)

3. **Dynamic formula problem**: The dynamic `T = (η × P) / v` formula is **too aggressive** at low speeds
   - At 37.6 m/s with 134 kW power and η=0.823
   - Dynamic thrust = (0.823 × 134,000) / 37.6 = **2,932 N**
   - But blending reduces this to: 0.545 × static + 0.455 × 2,932 N

## Root Cause

The **blend transition happens too early**. At climb speed (J=0.438), we're already 45% using the dynamic formula, which underestimates thrust because:
- The dynamic formula assumes propeller acts like a pure actuator disk
- Real propellers maintain better thrust at intermediate speeds due to blade element effects
- The blend should favor static/momentum theory longer (up to J~0.5-0.6)

## Realistic Solution Options

### Option 1: Adjust Blend Transition Points (Recommended)
Delay the blend transition to keep momentum theory dominant through climb:

**Current**:
```python
if advance_ratio < 0.20:
    blend = 0.05  # 5% dynamic
elif advance_ratio > 0.7:
    blend = 0.90  # 90% dynamic
else:
    blend = 0.05 + (advance_ratio - 0.20) * (0.90 - 0.05) / (0.7 - 0.20)
```

**Recommended**:
```python
if advance_ratio < 0.30:  # Extended static region
    blend = 0.05  # 5% dynamic
elif advance_ratio > 0.75:  # Delayed transition to dynamic
    blend = 0.90  # 90% dynamic
else:
    blend = 0.05 + (advance_ratio - 0.30) * (0.90 - 0.05) / (0.75 - 0.30)
```

This keeps the climb speed (J=0.438) at **blend=0.31** (31% dynamic, 69% static), maintaining more realistic thrust.

### Option 2: Improve Dynamic Formula
The dynamic formula needs an induced velocity correction:

**Current**:
```python
thrust_dynamic = (efficiency * power_watts) / (airspeed_mps + 0.1)
```

**Better**:
```python
# Account for induced velocity (slipstream effect)
# v_effective = v_airspeed + v_induced
# v_induced ≈ sqrt(thrust / (2 × ρ × A))
# Use iterative approach or approximation
thrust_dynamic = (efficiency * power_watts) / (airspeed_mps + 5.0)  # Rough +5 m/s for induced velocity
```

This increases the dynamic thrust at low speeds by reducing the divisor.

### Option 3: Increase Peak Efficiency (Simplest)
If the propeller is more efficient at climb speeds, increase `efficiency_cruise`:

**Current**:
```yaml
efficiency_static: 0.75
efficiency_cruise: 0.85
cruise_advance_ratio: 0.6
```

**Recommended**:
```yaml
efficiency_static: 0.75
efficiency_cruise: 0.90  # Higher peak efficiency
cruise_advance_ratio: 0.5  # Peak moved closer to climb speed
```

At J=0.438, this would interpolate to η≈0.88 instead of 0.823, giving ~7% more thrust.

### Option 4: Combination (Most Realistic)
Combine all three:

**Edit `config/aircraft/cessna172.yaml`:**
```yaml
propeller:
  type: "fixed_pitch"
  diameter_m: 1.905
  pitch_ratio: 0.6
  efficiency_static: 0.75
  efficiency_cruise: 0.88  # Increased from 0.85
  cruise_advance_ratio: 0.5  # Moved from 0.6 to favor climb
  static_thrust_multiplier: 4.3  # Keep unchanged for realistic ground acceleration
```

**Edit `src/airborne/systems/propeller/fixed_pitch.py` (lines 219-228):**
```python
# Blend between static and dynamic formulas smoothly
if advance_ratio < 0.30:  # Extended from 0.20
    blend = 0.05  # 95% static, 5% dynamic
elif advance_ratio > 0.75:  # Extended from 0.70
    blend = 0.90  # 10% static, 90% dynamic
else:
    # Smoother transition preserving momentum theory through climb
    blend = 0.05 + (advance_ratio - 0.30) * (0.90 - 0.05) / (0.75 - 0.30)
```

## Expected Results

With Option 4 (combination):
- **Ground acceleration**: Unchanged (still using multiplier=4.3 at J<0.05)
- **Climb thrust @ 69 kts**:
  - Efficiency: 0.875 (interpolated)
  - Blend: 0.236 (76% static, 24% dynamic)
  - Estimated thrust: ~2,400-2,500 N
  - **Climb rate: 700-750 fpm** ✓
- **Cruise performance**: Slightly improved efficiency

## Implementation Recommendation

**Start with Option 3** (quick config change):
```yaml
efficiency_cruise: 0.88
cruise_advance_ratio: 0.5
```

Test and verify climb improves to 650+ fpm without affecting ground roll.

**If needed, proceed to Option 4** (add code changes for blend points).

This approach maintains realism across all flight regimes:
- Realistic ground acceleration (multiplier unchanged)
- Better climb performance (efficiency curve optimized)
- Smooth transition to cruise (blend curve improved)

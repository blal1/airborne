# Cessna 172 Climb Performance Analysis

## Issue Summary
Aircraft is experiencing difficulty climbing - achieving only **276 fpm** vs. the expected **730 fpm** from the POH (Pilot's Operating Handbook).

## Telemetry Analysis

### Current Performance (Full Throttle Climb @ 69 kts)
- **Climb Rate**: 276 fpm (62% below expected)
- **Thrust**: 1,764 N
- **Drag**: 1,213 N
- **Weight**: 11,874 N (2,670 lbs)
- **Engine Power**: 150.4 HP @ 2,700 RPM
- **L/D Ratio**: 9.77 (good)

### Expected Performance (C172 POH)
- **Climb Rate**: 730 fpm (at sea level, Vy = 73 kts)
- **Weight**: 10,898 N (2,450 lbs) - reference weight
- **Required Thrust**: ~2,443 N

## Root Cause Analysis

### 1. **THRUST DEFICIT - PRIMARY ISSUE**
Current thrust is **38.5% too low** (679 N deficit)

**Problem**: The propeller is not generating enough thrust for the available engine power.

**Evidence**:
- Engine producing 150.4 HP (max rated power) ✓
- Engine at 2,700 RPM (max RPM) ✓
- But thrust only 1,764 N (should be ~2,443 N)

### 2. Weight Discrepancy (Secondary)
Sim aircraft is 220 lbs heavier than POH reference weight:
- Sim: 2,670 lbs
- POH: 2,450 lbs
- This adds ~97 N additional weight to overcome

### 3. Propeller Efficiency Issue
The current `static_thrust_multiplier: 4.3` is tuned for **static thrust** (v=0), but at climb speeds (69 kts), the propeller efficiency is lower than expected.

**Current config**:
```yaml
efficiency_static: 0.75    # At v=0
efficiency_cruise: 0.85    # At cruise (~110 kts)
cruise_advance_ratio: 0.6
```

The efficiency interpolation between static and cruise may not be optimized for climb speed (69 kts).

## Recommended Fixes

### Fix Option 1: Increase Static Thrust Multiplier (Quick Fix)
Increase `static_thrust_multiplier` to account for better thrust at climb speeds.

**Current**: 4.3
**Recommended**: 5.5-6.0 (increase by ~39%)

**Edit in `config/aircraft/cessna172.yaml`:**
```yaml
propeller:
  static_thrust_multiplier: 5.8  # Increased for better climb thrust
```

**Rationale**: The multiplier was tuned for static thrust (850 lbf / 3,780 N) but needs adjustment for dynamic flight conditions.

### Fix Option 2: Adjust Efficiency Curve (More Accurate)
Modify the efficiency curve to provide better thrust at climb speeds.

**Current**:
```yaml
efficiency_static: 0.75
efficiency_cruise: 0.85
cruise_advance_ratio: 0.6
```

**Recommended**:
```yaml
efficiency_static: 0.75
efficiency_cruise: 0.88     # Higher peak efficiency
cruise_advance_ratio: 0.4   # Peak efficiency at lower advance ratio (closer to climb speed)
```

This shifts the efficiency peak toward climb speeds rather than cruise speeds.

### Fix Option 3: Combination Approach (Recommended)
Combine both adjustments for realistic performance:

```yaml
propeller:
  type: "fixed_pitch"
  diameter_m: 1.905
  pitch_ratio: 0.6
  efficiency_static: 0.78           # Slightly higher static efficiency
  efficiency_cruise: 0.87           # Higher peak efficiency
  cruise_advance_ratio: 0.45        # Peak closer to climb speed
  static_thrust_multiplier: 5.5     # Moderate increase
```

### Fix Option 4: Reduce Aircraft Weight (If Realistic)
If the extra 220 lbs is not realistic for the simulation scenario:

**Check in `config/aircraft/cessna172.yaml`:**
```yaml
flight_model_config:
  weight_lbs: 2450.0  # Reduce to POH reference weight
```

This would reduce thrust requirement by ~97 N.

## Performance Targets

With fixes applied, expect:
- **Climb Rate**: 650-750 fpm (matching POH)
- **Thrust @ 69 kts**: 2,400-2,500 N
- **Climb Angle**: ~6° (realistic for C172)

## Implementation Priority

1. **Quick Test**: Try Fix Option 1 (increase `static_thrust_multiplier` to 5.8)
2. **Verify**: Run telemetry and check climb rate improves to 650+ fpm
3. **Fine-tune**: If needed, adjust to Option 3 for more realistic efficiency curve

## Additional Notes

### Other Observed Values (All Normal)
- **Drag**: 1,213 N (reasonable for 69 kts at climb pitch)
- **L/D Ratio**: 9.77 (good for climb configuration)
- **Engine Performance**: Running at max rated power
- **Propeller Diameter**: 1.905m (75 inches) - correct for C172

### Real C172 Static Thrust Reference
- Static thrust (v=0): ~850 lbf (3,780 N)
- Current sim static thrust: Tuned correctly with multiplier 4.3
- Problem is at higher airspeeds where propeller efficiency matters more

## Conclusion

The aircraft's poor climb performance is due to **insufficient thrust at climb speeds**. The propeller is not converting the engine's power efficiently at 69 kts. Increasing the `static_thrust_multiplier` to ~5.8 or adjusting the efficiency curve should restore realistic climb performance.

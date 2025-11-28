# Telemetry Analysis - 2025-10-26

## Test Run Summary

**Performance**: 30 seconds to reach 25 knots (expected: 20-25s)

## Telemetry Data Collected

### Engine State Progression

| Time | Throttle | RPM | Power | Combustion | Fuel | Elec | Mixture |
|------|----------|-----|-------|------------|------|------|---------|
| 16:54:39 | 0.00 | 543 | 0.0 HP | 22.2 | True | True | 1.00 |
| 16:54:40 | 0.00 | 598 | 0.0 HP | 22.1 | True | True | 1.00 |
| 16:54:41 | 0.00 | 600 | 0.0 HP | 22.1 | True | True | 1.00 |
| 16:54:42 | 0.00 | 600 | 0.0 HP | 22.1 | True | True | 1.00 |
| **16:54:43** | **0.15** | 600 | **13.9 HP** | 22.1 | True | True | 1.00 |
| 16:54:44 | 0.29 | 711 | 38.5 HP | 22.0 | True | True | 1.00 |
| 16:54:45 | 0.44 | 918 | 75.2 HP | 21.9 | True | True | 1.00 |
| 16:54:46 | 0.58 | 1137 | 123.2 HP | 21.8 | True | True | 1.00 |
| 16:54:47 | 0.73 | 1369 | 186.2 HP | 21.7 | True | True | 1.00 |
| 16:54:48 | 0.87 | 1612 | 261.9 HP | 21.6 | True | True | 1.00 |
| 16:54:49 | 1.00 | 1863 | 347.8 HP | 21.4 | True | True | 1.00 |
| 16:54:50 | 1.00 | 2121 | 395.9 HP | 21.3 | True | True | 1.00 |
| 16:54:51 | 1.00 | 2384 | 445.0 HP | 21.2 | True | True | 1.00 |
| 16:54:52 | 1.00 | 2651 | 495.2 HP | 21.0 | True | True | 1.00 |
| **16:54:53** | **1.00** | **2700** | **504.3 HP** | 20.9 | True | True | 1.00 |
| 16:54:54 | 1.00 | 2700 | 504.3 HP | 20.9 | True | True | 1.00 |

## Key Findings

### ✅ What's Working

1. **Throttle Input**: Reaching 1.00 (100%) as expected
2. **RPM Response**: Engine RPM increasing from idle (600) to max (2700) properly
3. **Combustion Energy**: Stable around 20-22 (healthy)
4. **Fuel System**: Available (True)
5. **Electrical System**: Available (True)
6. **Mixture**: Set to 1.00 (full rich)

### ❌ Critical Issue: Power Output TOO HIGH

**Expected Power at Full Throttle**:
- Engine: Lycoming O-360, 180 HP max (but code uses 160 HP)
- At 2700 RPM, throttle=1.0, mixture=1.0:
  - rpm_factor = 1.0
  - throttle_factor = 1.0
  - mixture_efficiency = 1.0 - abs(1.0 - 0.8) * 0.3 = **0.94**
  - Expected power = 160 × 1.0 × 1.0 × 0.94 = **150 HP**

**Actual Power Reported**: **504 HP** (3.35x too high!)

### Analysis

**Power Formula** (`simple_piston_plugin.py:556-575`):
```python
def _calculate_power(self) -> float:
    if not self.running:
        return 0.0

    max_power = 160.0  # Hardcoded
    rpm_factor = min(1.0, self.rpm / 2700.0)
    throttle_factor = self.throttle
    mixture_efficiency = 1.0 - abs(self.mixture - 0.8) * 0.3
    mixture_efficiency = max(0.5, min(1.0, mixture_efficiency))

    power = max_power * rpm_factor * throttle_factor * mixture_efficiency
    return max(0.0, power)
```

**Manual Calculation** (Python verification):
```
rpm_factor: 1.0
throttle_factor: 1.0
mixture_efficiency: 0.94
Calculated power: 150.4 HP
Telemetry showed: 504.3 HP
Ratio: 3.35x
```

**To produce 504 HP, the formula would need `max_power = 536 HP`!**

## Hypotheses

### Hypothesis 1: Telemetry Logging Bug
**What**: The `_calculate_power()` method being called by telemetry is different from what's in the source
**Evidence**:
- Source code shows `max_power = 160.0`
- Telemetry reports 504 HP
- .pyc bytecode compiled at 16:54, .py modified at 16:51

**Test**: Add inline logging directly in `_calculate_power()` to see intermediate values

### Hypothesis 2: Multiple Engine Instances
**What**: There might be multiple engine plugins running, each contributing power
**Evidence**: Config file has `max_power_hp: 180` in TWO places (line 34 and 197)

**Test**: Add logging in `initialize()` to count engine instances

### Hypothesis 3: Power Multiplier Elsewhere
**What**: Something else multiplies the power value before it reaches the propeller
**Evidence**: No direct evidence yet

**Test**: Search for power multiplication in physics plugin or propeller

### Hypothesis 4: Code/Bytecode Mismatch
**What**: Running code doesn't match source file
**Evidence**: .pyc bytecode is newer than .py source

**Test**: Delete .pyc files and restart simulator

## Performance Paradox

**CRITICAL OBSERVATION**:

If the engine were truly producing 504 HP (3.35x more than spec), the aircraft would accelerate MUCH FASTER than expected. But actual performance is:

- **Actual**: 30 seconds to 25 knots (TOO SLOW)
- **Expected**: 20-25 seconds to 25 knots

This suggests **the 504 HP reading is a logging/display error, NOT actual thrust being applied**.

## Recommended Next Steps

### Step 1: Add Detailed Power Calculation Logging

Modify `_calculate_power()` to log intermediate values:

```python
def _calculate_power(self) -> float:
    if not self.running:
        return 0.0

    max_power = 160.0
    rpm_factor = min(1.0, self.rpm / 2700.0)
    throttle_factor = self.throttle
    mixture_efficiency = 1.0 - abs(self.mixture - 0.8) * 0.3
    mixture_efficiency = max(0.5, min(1.0, mixture_efficiency))

    power = max_power * rpm_factor * throttle_factor * mixture_efficiency

    # DIAGNOSTIC: Log calculation details
    if throttle_factor > 0.9:  # Only log at full throttle
        logger.info(f"[POWER CALC] max_power={max_power}, rpm_factor={rpm_factor:.3f}, "
                   f"throttle_factor={throttle_factor:.3f}, mixture_eff={mixture_efficiency:.3f}, "
                   f"power={power:.1f}HP")

    return max(0.0, power)
```

### Step 2: Check Propeller Thrust

Add logging in `fixed_pitch.py` to see what power the propeller receives and what thrust it produces:

```python
def calculate_thrust(...):
    # ... existing code ...
    logger.info(f"[PROPELLER] power_hp={power_hp:.1f}, rpm={rpm:.0f}, "
               f"power_watts={power_watts:.0f}, thrust={thrust:.1f}N")
```

### Step 3: Clear Bytecode Cache

```bash
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
```

### Step 4: Investigate Physics Plugin

Check how `power_hp` from ENGINE_STATE message is used in physics calculations.

## Questions to Answer

1. **Why is reported power 3.35x higher than formula predicts?**
2. **Is the 504 HP actually being used for thrust calculation?**
3. **If yes, why is performance still slow despite massive power?**
4. **If no, what's the real power being used and why isn't it in telemetry?**

## Possible Root Causes (Ordered by Likelihood)

1. **Logging/Display Error**: `_calculate_power()` returns correct 150 HP, but logging shows wrong value
2. **Power Not Reaching Propeller**: Engine calculates power correctly, but propeller doesn't receive it
3. **Thrust Calculation Error**: Propeller receives power but thrust formula is wrong
4. **Drag Too High**: Thrust is correct but drag forces are excessive
5. **Ground Physics Still Wrong**: Despite our fixes, something still limiting acceleration

---

**Status**: NEEDS DEEPER INVESTIGATION
**Date**: 2025-10-26
**Next Action**: Add detailed logging to power calculation and propeller thrust

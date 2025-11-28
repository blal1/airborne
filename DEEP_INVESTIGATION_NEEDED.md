# Deep Investigation Required - Acceleration Still Too Slow

## Test Results (2025-10-26)

**Performance**:
- Time to 25 knots: **~30 seconds** (expected: 20-25s)
- Time to 55 knots: **UNABLE TO REACH** (expected: 40-45s)

## What We've Fixed So Far

### ✅ Phase 1: Ground Physics
- Removed 8,720 N of incorrect friction
- Reduced rolling resistance from 218 N to 163 N
- Fixed thrust direction
- Added 5% propeller thrust boost
- **Result**: 98.2% reduction in ground resistance

### ✅ Phase 2: Unit Tests
- Created 8 comprehensive tests
- **Result**: All passing, physics calculations correct

### ⚠️ Phase 3: Engine RPM Fixes (Multiple Attempts)
- **3a**: Prevented death spiral (minimum 300 RPM)
- **3b**: Added throttle response when > 50%
- **Result**: Engine starts, but performance still poor

## The Real Problem

After 3 iterations of fixes, acceleration is STILL too slow. This indicates a **fundamental issue** with:
1. Throttle input not reaching engine, OR
2. Combustion energy calculation broken, OR
3. Power calculation formula incorrect, OR
4. Something else entirely limiting power

## Evidence from Logs

```
Engine sound started at 5 RPM        ← Initial RPM very low
Engine started! RPM: 403              ← Starts correctly
[...]
Unable to reach 55 knots after 30+ seconds
```

This suggests:
- Engine CAN start (RPM > 400)
- But then doesn't produce enough power for acceleration
- Either RPM not increasing with throttle, OR power not scaling with RPM

## Root Cause Hypotheses

### Hypothesis 1: Throttle Not Reaching Engine ❓
**What**: The `=` key increases throttle, but engine never receives throttle > 0.5

**How to Test**:
Add logging to engine update:
```python
def update(self, dt: float) -> None:
    logger.info(f"Engine update: throttle={self.throttle:.2f}, rpm={self.rpm:.0f}, "
                f"combustion={self._combustion_energy:.1f}, running={self.running}")
```

**Expected if this is the problem**:
- Logs show `throttle=0.00` or `throttle=0.2` even when pressing `=`
- User pressing `=` but engine not receiving input

### Hypothesis 2: Combustion Energy Always Low ❓
**What**: `self._combustion_energy` is always < 10.0, preventing full power

**How to Test**:
Add logging to combustion calculation:
```python
def _update_combustion(self, dt: float) -> None:
    # ... existing code ...
    logger.info(f"Combustion: energy={self._combustion_energy:.2f}, "
                f"fuel_avail={self._fuel_available}, elec_avail={self._electrical_available}, "
                f"mixture={self.mixture:.2f}, throttle={self.throttle:.2f}")
```

**Expected if this is the problem**:
- Logs show `energy=2.5` or similar low values
- Fuel/electrical might be False
- Mixture might be wrong (too lean or too rich)

### Hypothesis 3: Power Formula Broken ❓
**What**: Power calculation doesn't produce enough HP even at 2700 RPM

**How to Test**:
Add logging to power calculation:
```python
def _calculate_power(self) -> float:
    if not self.running:
        return 0.0

    max_power = 160.0
    rpm_factor = min(1.0, self.rpm / 2700.0)
    throttle_factor = self.throttle
    mixture_efficiency = 1.0 - abs(self.mixture - 0.8) * 0.3

    power = max_power * rpm_factor * throttle_factor * mixture_efficiency

    logger.info(f"Power calc: rpm_factor={rpm_factor:.2f}, throttle_factor={throttle_factor:.2f}, "
                f"mixture_eff={mixture_efficiency:.2f}, power={power:.1f}HP")

    return max(0.0, power)
```

**Expected if this is the problem**:
- Logs show `power=15.0HP` or similar low values
- Even with rpm_factor=1.0, throttle_factor=1.0

### Hypothesis 4: RPM Not Increasing ❓
**What**: Our fix allows target_rpm to be 2700, but actual rpm stays low

**How to Test**:
Add logging to RPM update:
```python
def _update_rpm(self, dt: float) -> None:
    # Calculate target RPM
    if self.running:
        if self._combustion_energy > 10.0:
            target_rpm = self.idle_rpm + (self.max_rpm - self.idle_rpm) * self.throttle
        else:
            if self.throttle > 0.5:
                target_rpm = self.idle_rpm + (self.max_rpm - self.idle_rpm) * self.throttle
                # ...
            else:
                target_rpm = max(self.idle_rpm * 0.5, self._combustion_energy * 20.0)
    # ...

    logger.info(f"RPM update: target={target_rpm:.0f}, actual={self.rpm:.0f}, "
                f"throttle={self.throttle:.2f}, combustion={self._combustion_energy:.1f}")

    # ... rest of rpm integration ...
```

**Expected if this is the problem**:
- Logs show `target=2700, actual=650`
- RPM gradually increases but very slowly (inertia too high?)

## Recommended Next Steps

### Step 1: Add Comprehensive Logging

Modify `simple_piston_plugin.py` to add debug logging:

**In `update()` method** (~line 180):
```python
# Log every second (60 updates at 60 FPS)
if hasattr(self, '_debug_counter'):
    self._debug_counter += 1
else:
    self._debug_counter = 0

if self._debug_counter % 60 == 0:
    logger.info(f"[ENGINE] throttle={self.throttle:.2f}, rpm={self.rpm:.0f}, "
                f"power={self._calculate_power():.1f}HP, combustion={self._combustion_energy:.1f}, "
                f"running={self.running}")
```

### Step 2: Run Simulator and Collect Data

1. Start simulator
2. Apply full throttle (`=` key repeatedly)
3. Watch logs for 60 seconds
4. Look for patterns:
   - Does throttle increase to 1.0?
   - Does RPM reach 2700?
   - Does power reach ~160 HP?
   - What is combustion energy?

### Step 3: Analyze Data and Determine Root Cause

Based on log output, we can determine:
- **If throttle stays low**: Input system issue
- **If combustion energy stays low**: Fuel/electrical/mixture issue
- **If RPM stays low despite high target**: Inertia/integration issue
- **If power stays low despite high RPM**: Formula issue

## Alternative: Simplify Engine Logic

If investigation shows the combustion energy system is fundamentally broken, consider **simplifying the engine**:

```python
def _update_rpm(self, dt: float) -> None:
    """Simplified RPM calculation - just use throttle."""
    if self.running:
        # SIMPLE: RPM directly based on throttle, no combustion energy
        target_rpm = self.idle_rpm + (self.max_rpm - self.idle_rpm) * self.throttle
    elif self.starter_engaged and self._electrical_available:
        target_rpm = 400.0  # Cranking speed
    else:
        target_rpm = 0.0

    # RPM integration (keep existing inertia code)
    # ...
```

This removes all the complex combustion energy logic and just makes RPM follow throttle directly.

**Pros**:
- Simple, predictable behavior
- Guaranteed to work if throttle input is correct
- Easy to debug

**Cons**:
- Less realistic (no engine warmup, no stalling, etc.)
- Loses simulation fidelity

## Files to Investigate

1. **Throttle Input**: `src/airborne/core/input.py` - Does `=` key increase throttle?
2. **Message Passing**: Check CONTROL_INPUT messages reach engine
3. **Engine Plugin**: `src/airborne/plugins/engines/simple_piston_plugin.py`
   - Line ~180: `update()` method
   - Line ~440: `_update_rpm()` method
   - Line ~530: `_calculate_power()` method
   - Line ~500: `_update_combustion()` method

## Summary

We've fixed the ground physics (98.2% improvement) and prevented the engine from dying immediately, but **the core problem remains**: the engine doesn't produce enough power for proper acceleration.

**Next action**: Add comprehensive logging and collect data during a full throttle takeoff run to identify which component is failing.

**Expected outcome**: Logs will show either:
- Throttle not reaching 1.0
- Combustion energy stuck at low value
- RPM not increasing to 2700
- Power formula producing low output

Once we identify which of these is the problem, we can apply a targeted fix.

---

**Status**: NEEDS DEEP INVESTIGATION
**Date**: 2025-10-26
**Performance**: 30s to 25 knots (target: 20-25s), unable to reach 55 knots

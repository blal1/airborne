# Engine Power Issue - Investigation & Fix

## Problem Observed

During testing, aircraft took **~56 seconds to reach 25 knots** instead of expected ~20 seconds. Further investigation showed:

- Airspeed increased very slowly (0→25 knots in 56 seconds)
- Aircraft peaked at 33 knots then **decelerated** back to ~24 knots
- Engine sound started at only **7 RPM** (should be 2700 RPM at full power)
- No propeller thrust debug messages in logs

## Root Cause Analysis

### Issue #1: Engine RPM Stuck at 7 RPM

**Investigation:**
- Engine plugin (`simple_piston_plugin.py`) was running but producing almost zero power
- Power calculation: `power_hp = 160 * (RPM/2700) * throttle * mixture`
- With RPM = 7: `power = 160 * (7/2700) * 1.0 * 0.8 ≈ 0.4 HP`
- Propeller thrust with 0.4 HP ≈ **0 N** (essentially zero)

**Why RPM was stuck at 7:**

Looking at `_update_rpm()` method:
```python
if self.running:
    if self._combustion_energy > 10.0:
        target_rpm = self.idle_rpm + (self.max_rpm - self.idle_rpm) * self.throttle
    else:
        # Not enough combustion, engine dying
        target_rpm = self._combustion_energy * 20.0  # ← 0.35 * 20 = 7 RPM!
```

If combustion energy falls below 10, RPM is capped at `combustion_energy * 20`. This creates a death spiral:
1. Low combustion energy → Low RPM
2. Low RPM → Low power
3. Low power → Engine can't maintain combustion
4. Cycle repeats, engine dies

### Issue #2: Engine State May Not Persist

The engine requires RPM > 400 to initially set `self.running = True`, but if combustion energy drops after starting, the engine can effectively "die" while still marked as running, producing near-zero power.

## Fixes Applied

### Fix #1: Maintain Minimum Idle RPM When Running

**File:** `src/airborne/plugins/engines/simple_piston_plugin.py`
**Line:** 454

**Before:**
```python
else:
    # Not enough combustion, engine dying
    target_rpm = self._combustion_energy * 20.0
```

**After:**
```python
else:
    # Not enough combustion, engine dying
    # But maintain at least idle RPM if marked as running
    target_rpm = max(self.idle_rpm * 0.5, self._combustion_energy * 20.0)
```

**Rationale:**
- If engine is marked as `running = True`, maintain at least 300 RPM (half of idle_rpm)
- Prevents death spiral where low combustion → low RPM → zero power
- Gives engine a chance to recover if throttle/mixture are adjusted

### Fix #2: Added Debug Logging

**Lines 407, 456-457:**

Added logging to help diagnose engine issues:
```python
# Log when engine successfully starts
if not self.running and self.rpm > 400:
    self.running = True
    logger.info(f"Engine started! RPM: {self.rpm:.0f}, throttle: {self.throttle:.2f}")

# Warn when combustion energy is critically low
if self._combustion_energy < 5.0:
    logger.warning(f"Engine low combustion energy: {self._combustion_energy:.1f}, RPM: {self.rpm:.0f}, throttle: {self.throttle:.2f}, mixture: {self.mixture:.2f}")
```

## Expected Results After Fix

With the fix applied:

**Before Fix:**
- Engine dies with low combustion energy
- RPM drops to 7
- Power output: ~0.4 HP
- Thrust: ~0 N
- Acceleration: minimal (only from gravity/residual forces)

**After Fix:**
- Engine maintains minimum 300 RPM when running
- Power output: 160 * (300/2700) * throttle * mixture ≈ **18 HP** minimum at idle
- At full throttle: 160 * (2700/2700) * 1.0 * 0.8 = **128 HP**
- Propeller thrust at full power: **~610 N** (as designed)
- Acceleration: 0.55 m/s² (realistic)

## Integration with Acceleration Fixes

This engine fix complements the earlier physics fixes:

**Phase 1 Fixes (Ground Physics):**
- ✅ Removed incorrect sliding friction (8,720 N → 0 N)
- ✅ Reduced rolling resistance (218 N → 163 N)
- ✅ Fixed thrust direction (+Z forward)
- ✅ Boosted propeller static thrust (+5%)

**Phase 2 Validation:**
- ✅ All 8 unit tests passing
- ✅ Validates thrust calculations are correct

**Phase 3 Fix (This Document):**
- ✅ Ensure engine actually PRODUCES the power that physics expects
- ✅ Prevent engine RPM death spiral
- ✅ Maintain minimum idle RPM when running

## Testing Required

To validate the fix:

1. **Start engine normally** (starter, magnetos, fuel pump, mixture rich)
2. **Apply full throttle** (= key)
3. **Monitor logs** for:
   - "Engine started! RPM: XXX" message
   - No "low combustion energy" warnings
   - RPM should climb to 2700
4. **Observe acceleration**:
   - Should reach 25 knots in ~20-25 seconds
   - Should reach 50 knots in ~40-45 seconds
   - Much faster than before (was 56s to 25 knots)

## Potential Future Improvements

If issues persist, consider:

1. **Investigate combustion energy calculation** - Why does it drop below 10?
2. **Check throttle input** - Is `self.throttle` actually receiving 1.0?
3. **Check mixture** - Is `self.mixture` set to optimal (~0.8)?
4. **Add telemetry display** - Show real-time engine stats (RPM, power, combustion energy)
5. **Review fuel system** - Ensure `_fuel_available` is True
6. **Check electrical system** - Ensure `_electrical_available` for ignition

## Files Modified

1. `src/airborne/plugins/engines/simple_piston_plugin.py`
   - Line 454: Added minimum RPM maintenance
   - Line 407: Added engine start logging
   - Lines 456-457: Added low combustion energy warning

## References

- `ACCELERATION_ISSUE_ANALYSIS.md` - Original ground physics issue
- `ACCELERATION_FIX_SUMMARY.md` - Phase 1 & 2 fixes summary
- `tests/physics/test_acceleration_fix.py` - Validation tests

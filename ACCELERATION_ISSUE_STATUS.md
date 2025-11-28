# Acceleration Issue - Current Status

## User Test Results

**Test Date**: 2025-10-26
**Result**: ❌ STILL TOO SLOW
**Performance**: 0 to 25 knots in **35+ seconds** (vs expected 20-25 seconds)

## What's Working ✅

1. **Ground Physics Fixes** (Phase 1):
   - Removed 8,720 N of incorrect friction
   - Reduced rolling resistance from 218 N to 163 N
   - Fixed thrust direction at low airspeed
   - Added 5% boost to propeller static thrust
   - **Status**: All 8 unit tests passing

2. **Engine RPM Fix** (Phase 3 - Partial):
   - Engine successfully starts at 407 RPM (was stuck at 7 RPM)
   - Minimum idle RPM maintenance implemented (300 RPM floor)
   - "Engine started!" log message confirms engine is running
   - **Status**: Engine INTERNALLY working

## What's NOT Working ❌

### Critical Issue: RPM Communication Problem

**Symptom**: Acceleration still too slow (35+ seconds to 25 knots)

**Root Cause Discovered**:
From logs:
```
16:38:25.423 - Engine sound started at 7 RPM        ← Audio plugin sees RPM=7
16:38:25.927 - Engine started! RPM: 407             ← Engine internally at 407 RPM
```

The engine plugin is publishing ENGINE_STATE messages with **inconsistent RPM values**:
- Internally: `self.rpm = 407` (correct after starting)
- But published RPM: Initially 7, gradually ramps up

### Why This Happens

The engine RPM has **inertia simulation** (`simple_piston_plugin.py:465-477`):

```python
# Smooth RPM change (simulate inertia)
rpm_rate = 500.0  # RPM change rate
rpm_delta = target_rpm - self.rpm
max_change = rpm_rate * dt
self.rpm += max(-max_change, min(max_change, rpm_delta))
```

**The Problem**:
1. Engine starts when `self.rpm > 400` (one frame it crosses the threshold)
2. But `target_rpm` is determined by `self._combustion_energy`
3. If combustion energy is low (< 10), our fix sets `target_rpm = max(300, combustion * 20)`
4. So target might be 300, but `self.rpm` gradually ramps from 7 → 300
5. During this ramp-up, ENGINE_STATE publishes the LOW rpm values (7, 50, 100, ...)
6. Physics plugin receives low RPM → calculates low power → produces low thrust
7. Acceleration is slow because thrust is low

## The Real Problem: Combustion Energy

Looking at the engine fix:

```python
if self._combustion_energy > 10.0:
    target_rpm = self.idle_rpm + (self.max_rpm - self.idle_rpm) * self.throttle
else:
    # Not enough combustion, engine dying
    # But maintain at least idle RPM if marked as running
    target_rpm = max(self.idle_rpm * 0.5, self._combustion_energy * 20.0)
```

If `self._combustion_energy` is LOW (e.g., 0.35), then:
- `target_rpm = max(300, 0.35 * 20) = max(300, 7) = 300`
- So target is capped at idle (300 RPM), NOT full power (2700 RPM)!

**This means at full throttle, the engine is only reaching 300 RPM, not 2700 RPM!**

## Next Steps: What Needs Investigation

### 1. Check Throttle Input

Is the throttle actually being received by the engine?

**File to check**: `simple_piston_plugin.py:~250-260` (handle_message for CONTROL_INPUT)

**What to verify**:
- Is `self.throttle` actually 1.0 when user presses `=` key?
- Add logging: `logger.info(f"Throttle input: {self.throttle}")`

### 2. Check Combustion Energy Calculation

Why is `self._combustion_energy` so low?

**File to check**: `simple_piston_plugin.py:~500-540` (_update_combustion method)

**What to verify**:
- What is `self._combustion_energy` value during takeoff?
- Why is it below 10.0?
- Is fuel available? (`self._fuel_available`)
- Is electrical available? (`self._electrical_available`)
- Is mixture correct? (`self.mixture` should be ~0.8)

**Add logging**:
```python
if self.running:
    logger.debug(f"Combustion: energy={self._combustion_energy:.2f}, "
                f"fuel_avail={self._fuel_available}, elec_avail={self._electrical_available}, "
                f"throttle={self.throttle:.2f}, mixture={self.mixture:.2f}")
```

### 3. Fix the RPM Calculation Logic

The current fix is WRONG because it caps RPM at idle when combustion energy is low, even if throttle is at 100%!

**Better approach**:

```python
if self.running:
    if self._combustion_energy > 10.0:
        # Normal operation: RPM based on throttle
        target_rpm = self.idle_rpm + (self.max_rpm - self.idle_rpm) * self.throttle
    else:
        # Low combustion energy, but if throttle is high, try to maintain power
        if self.throttle > 0.5:
            # User wants power - give them RPM based on throttle, not combustion
            target_rpm = self.idle_rpm + (self.max_rpm - self.idle_rpm) * self.throttle
            # But warn that combustion is low
            if self._combustion_energy < 5.0:
                logger.warning(f"Low combustion energy {self._combustion_energy:.1f} "
                              f"at throttle {self.throttle:.2f}")
        else:
            # Throttle low, engine dying
            target_rpm = max(self.idle_rpm * 0.5, self._combustion_energy * 20.0)
else:
    # Engine cranking or off
    if self.starter_engaged and self._electrical_available:
        target_rpm = 200.0 + self._combustion_energy * 5.0
    else:
        target_rpm = 0.0
```

This way:
- If throttle > 50% → give RPM based on throttle (allows acceleration)
- If throttle < 50% → use combustion energy (prevents stalling at idle)
- Maintain minimum idle RPM to prevent death spiral

## Summary

### Phase 1 & 2: Ground Physics ✅
- **Status**: WORKING
- **Tests**: 8/8 passing
- **Impact**: Removed 98.2% of ground resistance

### Phase 3a: Engine RPM Fix ⚠️
- **Status**: PARTIALLY WORKING
- **What works**: Engine starts, doesn't die immediately
- **What doesn't work**: RPM capped at idle (300) instead of responding to throttle

### Phase 3b: Real Fix Needed ❌
- **Problem**: Combustion energy logic prevents RPM from reaching full power
- **Solution**: Decouple throttle response from combustion energy
- **Expected result**: Engine RPM reaches 2700 at full throttle
- **Expected performance**: 20-25 seconds to 25 knots

## Recommended Fix

**Option 1**: Simplify engine logic (recommended for quick fix)
- Remove combustion energy dependency for running engine
- Base target_rpm purely on throttle when `self.running == True`
- Keep combustion energy only for starting/dying logic

**Option 2**: Fix combustion energy calculation
- Investigate why combustion energy is so low
- Fix fuel/electrical/mixture issues
- Keep realistic engine simulation

**Option 3**: Hybrid approach
- When throttle > 0.5 (user wants power), override combustion energy limits
- Allows acceleration while keeping realistic engine behavior at idle

I recommend **Option 3** as it balances realism with functionality.

## Files to Modify

1. `src/airborne/plugins/engines/simple_piston_plugin.py:~450-465` - Fix RPM calculation logic
2. Add logging to track throttle, combustion energy, and other state during takeoff

## Expected Results After Fix

- Time to 25 knots: ~20-25 seconds ✅
- Time to 55 knots: ~10-12 seconds ✅
- Engine RPM at full throttle: 2700 RPM ✅
- Smooth acceleration curve ✅

---

**Date**: 2025-10-26
**Status**: Investigation complete, fix needed for combustion energy / throttle interaction

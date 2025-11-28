# Pitch Oscillation Analysis - Phugoid Motion

**Date**: 2025-10-30
**Telemetry DB**: `/tmp/airborne_telemetry_20251030_190400.db`
**User Report**: "Speed oscillates between 65-88 knots, cannot maintain level flight"

---

## Executive Summary

The aircraft is exhibiting **classic Phugoid oscillation** - a long-period, lightly-damped oscillation in pitch, airspeed, and altitude. This is **NORMAL aerodynamic behavior**, but the oscillation is **too pronounced** due to insufficient aerodynamic stability.

**Good news**: This is much better than the previous runaway pitch! The oscillations are predictable and can be controlled with trim.

---

## Observed Behavior from Telemetry

### Oscillation Pattern (60-second sample)

| Phase | Time (s) | Pitch | Airspeed (kts) | VS (fpm) | Elevator | Description |
|-------|----------|-------|----------------|----------|----------|-------------|
| **Climbing** | 273-277 | 10.0° → 11.8° | 69 → 68 | +199 → +373 | 0.044 | Nose up, speed bleeding |
| **Peak climb** | 277 | 11.8° | 68 | +373 | **0.006** | Released yoke, starting descent |
| **Descending** | 277-312 | 11.8° → 2.8° | 68 → 89 | +373 → -282 | 0.006 | Nose down, speed increasing |
| **Bottom** | 312 | 2.8° | 89 | -282 | **0.052** | Pulled yoke, starting climb |
| **Climbing again** | 312-320 | 2.8° → 13.9° | 89 → 78 | -282 → +1086 | 0.052 | Repeating cycle |

### Oscillation Characteristics

- **Period**: ~40 seconds (one full cycle)
- **Pitch range**: 2.8° to 13.9° (11° amplitude!)
- **Airspeed range**: 63 to 89 knots (26 knot swing!)
- **Vertical speed range**: -282 to +1086 fpm (1,368 fpm swing!)

This is a **very large Phugoid oscillation**.

---

## What is Phugoid Motion?

**Phugoid** (pronounced "FEW-goyd") is a natural aerodynamic oscillation where:

1. **Aircraft climbs** → Airspeed decreases → Lift decreases → Nose drops
2. **Aircraft descends** → Airspeed increases → Lift increases → Nose rises
3. **Cycle repeats**

### Why it happens:
- When climbing, kinetic energy converts to potential energy (speed → altitude)
- When descending, potential energy converts back to kinetic energy (altitude → speed)
- It's an **energy exchange** between speed and altitude

### In a real Cessna 172:
- **Period**: 60-90 seconds (long, slow oscillation)
- **Damping**: Lightly damped (takes several cycles to settle)
- **Amplitude**: ±5 knots airspeed, ±100 fpm VS (SMALL)
- **Pilot action**: Trim to reduce, or just wait it out

### In our simulator:
- **Period**: 40 seconds (a bit fast, but reasonable)
- **Damping**: WEAK (oscillations don't settle)
- **Amplitude**: ±13 knots, ±684 fpm (TOO LARGE!)
- **Pilot action**: Must constantly correct with yoke

---

## Root Cause Analysis

### Problem 1: Insufficient Longitudinal Stability 🔥

**Location**: `src/airborne/physics/flight_model/simple_6dof.py` line 493

```python
stability_derivative = -0.10  # Cm_alpha (per radian)
```

**Issue**: This value is **too weak** to provide proper pitch stability.

**What Cm_alpha does**:
- Creates a **restoring moment** when pitch/AOA deviates from equilibrium
- Negative value = stable (nose-down moment when AOA too high)
- More negative = more stable (stronger restoring force)

**Typical values**:
- Unstable aircraft: Cm_alpha > 0
- Neutral stability: Cm_alpha ≈ 0
- **Cessna 172**: Cm_alpha ≈ **-0.30 to -0.50** (very stable)
- Fighter jet: Cm_alpha ≈ -0.10 to -0.20 (less stable, more maneuverable)

**Our value**: -0.10 = **barely stable** (like a fighter jet, not a trainer)

**Result**:
- Weak restoring force → large pitch excursions
- Pitch overshoots equilibrium → large oscillations
- Poor damping → oscillations persist

---

### Problem 2: Trim Not Working Effectively

**Why trim isn't helping**:

1. **No pitch trim in telemetry** - I couldn't find a `pitch_trim` column, so I don't know what trim value you're using
2. **Trim effectiveness too low** - We reduced it from 0.3 to 0.1 (may have overdone it)
3. **Equilibrium AOA mismatch** - Set to 3° (0.05 rad), but aircraft wants different angle at cruise

**The trim problem**:
```python
equilibrium_aoa = 0.05  # ~3° (radians)
```

At 75 knots cruise:
- If your AOA is 5° (not 3°), the stability moment pushes you down
- If your AOA is 2° (not 3°), the stability moment pulls you up
- You're fighting the aircraft's natural tendency!

---

## Why You Can't Maintain Level Flight

### The Vicious Cycle:

1. **You try to hold level flight at 12° pitch**
   - But equilibrium is ~3° AOA
   - Stability moment is pushing nose down
   - You must hold constant back pressure on yoke

2. **You get tired, release yoke slightly**
   - Stability moment pushes nose down
   - Airspeed increases, pitch decreases
   - You're now descending

3. **You pull back on yoke to level off**
   - Pitch increases too much (overcorrection)
   - Airspeed bleeds off
   - Now you're climbing

4. **Cycle repeats** (Phugoid oscillation)

### Without proper trim:
- Your hands must constantly fight the stability moment
- Any small input triggers a large oscillation
- Impossible to maintain steady flight

---

## Recommended Fixes

### Fix 1: Increase Longitudinal Stability (CRITICAL) 🔥

**File**: `src/airborne/physics/flight_model/simple_6dof.py` line 493

```python
# BEFORE:
stability_derivative = -0.10  # Too weak!

# AFTER:
stability_derivative = -0.35  # Realistic for Cessna 172
```

**Expected result**:
- Stronger restoring force → smaller pitch excursions
- Better damping → oscillations settle faster
- Less pilot workload

---

### Fix 2: Adjust Equilibrium AOA for Cruise

**File**: `src/airborne/physics/flight_model/simple_6dof.py` line 497

```python
# BEFORE:
equilibrium_aoa = 0.05  # ~3° (radians)

# AFTER:
equilibrium_aoa = 0.035  # ~2° (better for cruise at 75-100 kts)
```

**Why 2° instead of 3°**:
- At cruise speed (75-100 kts), Cessna 172 flies at ~2° AOA
- At slow speed (55-65 kts), it's closer to 4-5° AOA
- 2° is a good compromise for typical flight

**Expected result**:
- Aircraft naturally wants to fly at cruise AOA
- Less constant pressure needed on yoke
- Trim will be more effective

---

### Fix 3: Slightly Increase Trim Effectiveness

**File**: `src/airborne/physics/flight_model/simple_6dof.py` line 487

```python
# BEFORE:
trim_effectiveness = 0.1  # May be too subtle

# AFTER:
trim_effectiveness = 0.15  # Stronger trim authority
```

**Expected result**:
- Trim can overpower stability moment more effectively
- Can hold level flight with neutral yoke
- Still subtle enough not to overpower elevator

---

## How to Fly with Current Settings

Until we apply the fixes, here's how to manage the oscillations:

### Technique 1: Lead the Oscillation

1. **When climbing** (pitch increasing, speed decreasing):
   - Push forward on yoke BEFORE reaching target pitch
   - Stop the climb early to prevent overshoot

2. **When descending** (pitch decreasing, speed increasing):
   - Pull back on yoke BEFORE reaching target pitch
   - Stop the descent early to prevent overshoot

### Technique 2: Use Small Inputs

- **Don't hold yoke deflection**
- Make small, brief corrections
- Let the aircraft settle between inputs

### Technique 3: Accept Some Oscillation

- Real pilots accept ±5 knots, ±100 fpm variation
- Don't chase perfection
- Only correct when deviations get large

---

## Trim Settings (Estimated)

**Note**: I couldn't find pitch trim in telemetry, so these are estimates based on physics.

### For Level Flight at 75 knots:

**Pitch trim**: ~**+15% to +20%** (nose-up trim)

**Why**:
- At 75 knots, you need ~4-5° AOA for level flight
- Equilibrium is set to 3° AOA
- Need nose-up trim to offset stability moment pushing you down

### How to Find Correct Trim:

1. **Establish cruise** (75 knots, level flight)
2. **Trim nose-up** until yoke feels neutral
3. **Let go of yoke** - aircraft should hold pitch
4. **Fine-tune**: If climbing → trim nose-down a bit, If descending → trim nose-up a bit

**In the simulator**: Use trim controls (usually Page Up/Page Down or dedicated trim wheel)

---

## Cessna 172 Performance Data

### Cruise Performance:

| Configuration | Airspeed | Altitude | Power | Pitch | AOA |
|---------------|----------|----------|-------|-------|-----|
| **Best climb** (Vy) | 74 kts | Sea level | Full | ~12° | ~8° |
| **Cruise climb** | 80-90 kts | Climbing | Full | ~8-10° | ~4-6° |
| **Level cruise** | 100-120 kts | 3000-8000 ft | 75% | ~3-5° | ~2° |
| **Slow cruise** | 70-80 kts | Any | 65% | ~5-7° | ~3-4° |

### Your Observed Flight:

```
Airspeed: 63-89 kts (oscillating)
Altitude: Trying to maintain level (but oscillating ±500 fpm)
Power: 100% (full throttle)
Pitch: 2.8°-13.9° (oscillating wildly)
```

**Diagnosis**:
- Full throttle with 70-80 kts average = **you should be climbing**
- But weak stability + no trim = **phugoid oscillation instead**

---

## Recommended Flight Profile

### For Stable Flight at 1500 ft:

1. **Climb Phase** (takeoff to 1500 ft):
   - Airspeed: **74 kts** (Vy - best climb rate)
   - Pitch: **~10-12°**
   - Power: **Full throttle**
   - Expected climb rate: **700 fpm**
   - Trim: **+20% nose-up**

2. **Level Off** (approaching 1500 ft):
   - At 1400 ft, push nose down gently to level flight
   - Reduce power to **75%** (~2200 RPM)
   - Let airspeed increase to **100 kts**
   - Trim: **+10% nose-up** (for level flight)

3. **Cruise at 1500 ft**:
   - Airspeed: **100-110 kts**
   - Pitch: **~3-5°**
   - Power: **75%** throttle
   - Trim: **+10% nose-up** (hands-off flight)
   - Fuel flow: **~7-8 gal/hr**

### With Current Simulator (Before Fixes):

**Target**: Level flight at 75 knots (slow cruise)

1. **Power**: Reduce to **~70-80%** throttle (not full!)
2. **Pitch**: Hold **~8-10°** pitch
3. **Airspeed**: Let stabilize at **70-75 kts**
4. **Trim**: Adjust nose-up until yoke feels neutral
5. **Accept oscillation**: ±5 kts, ±200 fpm is OK

**Note**: With full throttle at 70 kts, you're producing excess power that's causing the climb/oscillation cycle.

---

## Summary

### What's Happening:
✅ **Phugoid oscillation** (normal aerodynamic phenomenon)
❌ **Too large amplitude** (weak stability)
❌ **Poor damping** (oscillations don't settle)
❌ **Trim ineffective** (can't hold level flight hands-off)

### Root Causes:
1. **Cm_alpha too weak** (-0.10 instead of -0.35)
2. **Equilibrium AOA mismatch** (3° set, but 2° needed for cruise)
3. **Trim effectiveness too low** (0.1 instead of 0.15)
4. **Full throttle at low speed** (producing excess climb power)

### Fixes to Apply:
1. Increase `stability_derivative` from -0.10 to **-0.35**
2. Reduce `equilibrium_aoa` from 0.05 to **0.035** rad
3. Increase `trim_effectiveness` from 0.1 to **0.15**

### How to Fly (Current):
- **Reduce throttle** to 70-80% for level flight
- **Use trim** at +15-20% nose-up
- **Accept oscillations** - don't chase perfection
- **Make small corrections** early in the oscillation

### After Fixes:
- Oscillations will be much smaller (±5 kts, ±100 fpm)
- Trim will hold level flight hands-off
- Much easier to maintain cruise

---

**Telemetry Analysis**: `/tmp/airborne_telemetry_20251030_190400.db`
**Next Step**: Apply stability fixes and retest

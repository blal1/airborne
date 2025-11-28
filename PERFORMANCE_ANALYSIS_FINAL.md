# Performance Analysis - Final Test Results
## Date: 2025-10-27

## ✅ Fixes Applied Successfully

### 1. Blend Discontinuity Bug - FIXED ✅
**Before**: Thrust dropped from 787N → 655N at 17.2 m/s (132N loss, 17%)
**After**: Smooth transition 787N → 784N → 780N (no discontinuity)

The blend now smoothly transitions from 0.05 → 0.30 across the takeoff range with no jumps.

### 2. Airspeed Announcements - FIXED ✅
**Before**: Rounded to nearest 5 knots ("airspeed 35 knots")
**After**: Exact knots ("airspeed 37 knots")

Changed in `speech_messages.py` line 167.

## ❌ CRITICAL ISSUE: Acceleration Still Too Slow

### Test Results
**Observed Performance**:
- **60 seconds** to reach 35 knots (18 m/s)
- **~13 seconds** for 0-10 m/s (0-20 knots)
- **~25 seconds** for 10-20 m/s (20-40 knots)

**Expected Performance** (Real C172):
- **13-15 seconds** TOTAL to reach 55 knots (rotation speed)
- **~5-6 seconds** for 0-20 knots
- **~8-9 seconds** for 20-55 knots

**Current performance is ~4x too slow!**

## 📊 Force Analysis from Logs

### Thrust Profile (Full Power, 150.4HP @ 2700 RPM)

| Speed | Thrust | Blend | Correction | Notes |
|-------|--------|-------|------------|-------|
| 0 m/s | 943N | static | 1.450 | ✅ Good static thrust |
| 5 m/s | 933N | 0.05 | 1.435 | ✅ Maintaining thrust |
| 10 m/s | 875N | 0.05 | 1.329 | ⚠️ Dropping faster than expected |
| 15 m/s | 810N | 0.10 | 1.221 | ⚠️ Significant drop |
| 20 m/s | 747N | 0.21 | 1.115 | ⚠️ 20% loss from static |
| 25 m/s | 691N | 0.30 | 1.031 | ⚠️ 27% loss from static |

**Observation**: Thrust drops 27% by 25 m/s (50 knots), which is excessive for a fixed-pitch propeller.

### Expected vs Actual Acceleration

| Phase | Speed Range | Expected Time | Actual Time | Ratio |
|-------|-------------|---------------|-------------|-------|
| Takeoff roll start | 0-20 kts | 5-6 sec | 13 sec | 2.3x slow |
| Mid takeoff | 20-40 kts | 8-9 sec | 25 sec | 2.8x slow |
| Full takeoff | 0-55 kts | 13-15 sec | ~60 sec (est) | 4.0x slow |

## 🔍 Root Cause Analysis

### Possible Causes (in order of likelihood):

#### 1. **Drag Coefficient Too High** ⭐ MOST LIKELY
From `cessna172.yaml`:
```yaml
drag_coefficient: 0.042  # Cd0 - parasite drag
```

**Issue**: This might be too high. Real C172:
- Clean configuration: Cd0 ≈ 0.027-0.030
- With gear/struts (fixed gear): Cd0 ≈ 0.035-0.038
- Current config: 0.042 (17% higher than realistic!)

**Impact**: At 20 m/s, drag force = 0.5 × ρ × v² × S × Cd
- Current (Cd=0.042): Drag = 235N
- Realistic (Cd=0.035): Drag = 196N
- **Extra 39N of drag** (20% more resistance)

#### 2. **Induced Drag Missing or Too High**
The induced drag calculation might be adding excessive drag during takeoff when angle of attack is high.

From earlier investigations, we know induced drag was added but the coefficient might be too aggressive.

#### 3. **Rolling Resistance**
From `ground_physics.py`:
```python
"asphalt": 0.010  # Rolling resistance coefficient
```

This was already reduced from 0.015 to 0.010 (realistic for aircraft tires).
Rolling resistance at 20 m/s = ~120N

**This is reasonable and realistic.**

#### 4. **Mass Too High**
From logs: `mass=1211.1kg` (2670 lbs)

This is heavier than typical C172 takeoff weight:
- Empty + pilot + fuel: ~2400-2500 lbs (1090-1135 kg)
- Max gross: 2550 lbs (1157 kg)

**Current: 1211kg = 2670 lbs** - This is 120 lbs over max gross weight!

**Where is the extra weight coming from?**

## 🎯 Recommended Fixes (Priority Order)

### Fix 1: Reduce Parasite Drag Coefficient ⭐ HIGH PRIORITY
**Current**: `drag_coefficient: 0.042`
**Recommended**: `drag_coefficient: 0.035`

**Expected Impact**: +20% acceleration in mid-speed range (20-40 knots)

### Fix 2: Investigate Mass Calculation 🔍 HIGH PRIORITY
Aircraft is 120 lbs over max gross weight. Check:
1. Weight & balance calculation
2. Initial fuel/payload settings
3. Empty weight configuration

**Expected Impact**: +10-15% acceleration across all speeds

### Fix 3: Review Induced Drag Calculation
Check if induced drag coefficient is realistic for ground roll (low angle of attack).

**Expected Impact**: +5-10% acceleration in low-speed range

## 📝 Testing Plan

### Step 1: Reduce drag coefficient to 0.035
```yaml
# config/aircraft/cessna172.yaml
drag_coefficient: 0.035  # Realistic for C172 with fixed gear
```

**Expected result**: 0-55 knots in ~20-25 seconds (still slow but better)

### Step 2: Fix mass issue (investigate weight calculation)
**Expected result**: 0-55 knots in ~15-18 seconds (closer to realistic)

### Step 3: Fine-tune if needed
Adjust thrust multiplier or other parameters based on results.

## 🎲 Quick Estimates

### Current Configuration
- Static thrust: 943N ✅
- Thrust at 25m/s: 691N
- Drag at 25m/s: ~250N (too high!)
- Rolling resistance: ~100N
- **Net force at 25m/s**: 691 - 250 - 100 = **341N**
- **Acceleration at 25m/s**: 341N / 1211kg = **0.28 m/s²** ⚠️ Too low!

### With Reduced Drag (Cd=0.035)
- Thrust at 25m/s: 691N (unchanged)
- Drag at 25m/s: ~208N (17% reduction)
- Rolling resistance: ~100N
- **Net force at 25m/s**: 691 - 208 - 100 = **383N**
- **Acceleration at 25m/s**: 383N / 1211kg = **0.32 m/s²** Still low

### With Reduced Drag + Correct Mass (1135kg)
- **Net force at 25m/s**: 383N
- **Acceleration at 25m/s**: 383N / 1135kg = **0.34 m/s²** Better but still not enough

### Real C172 Performance
- Expected acceleration at mid-speed: **~0.50-0.60 m/s²**
- Our best case above: **0.34 m/s²**
- **Still 40% short!**

## 🤔 Additional Considerations

Something else might be wrong. Even with both fixes, we're still ~40% short of realistic performance.

**Possible additional issues**:
1. **Thrust calculation** - Are we losing thrust too quickly with speed?
2. **Lift-induced drag** - Is the induced drag model too aggressive?
3. **Time step issues** - Is physics integration causing issues?
4. **Engine power curve** - Is the engine delivering full power?

**Recommendation**: Apply drag and mass fixes first, then investigate further if still too slow.

---

**Next Steps**:
1. Reduce `drag_coefficient` from 0.042 to 0.035
2. Investigate why mass is 1211kg (should be ~1135kg)
3. Test and analyze results
4. If still slow, investigate thrust/drag balance more deeply

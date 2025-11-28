# Propeller Fix & Remaining Issue - 2025-10-27

## ✅ FIXED: Propeller Not Loading

### Root Cause
The propeller configuration was never being loaded due to incorrect config path in `main.py:232`:

**Before (BROKEN):**
```python
physics_config = config.get("physics", {})  # Empty! No "physics" section exists
propeller_config = physics_config.get("propeller", {})  # Always empty
```

**After (FIXED):**
```python
propeller_config = config.get("aircraft", {}).get("propeller", {})  # Correct path!
```

### Files Modified
1. `src/airborne/main.py` - Line 232: Fixed propeller config path
2. `src/airborne/plugins/core/physics_plugin.py` - Added diagnostic logging
3. `src/airborne/systems/propeller/fixed_pitch.py` - Removed >100N threshold, added detailed logging  
4. `src/airborne/physics/flight_model/simple_6dof.py` - Added propeller vs fallback logging

### Verification
✅ Propeller model now properly attached at startup:
```
Propeller model attached to flight model: diameter=1.905m, 
efficiency_static=0.72, efficiency_cruise=0.85
```

✅ Propeller thrust calculations working:
```
[PROPELLER] power_in=150.4HP rpm=2700 airspeed=6.5m/s 
efficiency=0.720 advance_ratio=0.073 power_watts=112153W THRUST=637.2N
```

✅ Flight model using propeller (not fallback):
```
[FLIGHT_MODEL] Using PROPELLER: thrust=637.2N from power=150.4HP rpm=2700
```

## ❌ REMAINING ISSUE: Slow Acceleration

### Observed Performance
- Full throttle reached: 8 seconds after engine start
- Time from full power to 9 knots: **17 seconds**
- Expected: ~10-12 seconds
- **Issue: 40% slower than expected**

### What's Working
✅ Engine: 150.4 HP @ 2700 RPM  
✅ Propeller: 637-648N thrust (correct magnitude)  
✅ Propeller efficiency: 0.72-0.75 (realistic)  
✅ Power transmission: Engine → Physics plugin working  

### What's NOT Working
❌ **Ground physics logs: COMPLETELY MISSING**
- No `[PHYSICS] ground_force` logs
- No `[PHYSICS] Ground contact` logs  
- No ground acceleration or velocity logs

### Root Cause Analysis
The aircraft is generating correct thrust (637N), but ground physics is NOT being applied!

**Possible causes:**
1. **Aircraft not detected as "on_ground"** - Ground physics only runs when `state.on_ground == True`
2. **Terrain collision not working** - Aircraft might think it's airborne
3. **Ground physics code path not executing** - Logic error in physics plugin

### Evidence
Looking at `physics_plugin.py:353-407`, ground physics should log:
```python
if state.on_ground and self.ground_physics:
    # Should log ground contact info
    # Should log ground forces  
    # Should log acceleration
```

**None of these logs appear** → Aircraft is NOT on ground!

### Next Steps
Need to investigate:
1. Why `state.on_ground` is False
2. Terrain collision detection
3. Initial spawn position (altitude)
4. Whether aircraft is falling through terrain

## Summary

**Fixed:** Propeller now loads and generates realistic thrust ✅  
**Remaining:** Ground physics not executing → slow acceleration ❌  
**Impact:** Propeller fix was successful but revealed ground detection bug  

---
Date: 2025-10-27
Status: Propeller working, ground physics investigation needed

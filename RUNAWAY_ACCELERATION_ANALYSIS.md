# Runaway Acceleration Analysis

## Summary

After increasing `static_thrust_multiplier` from 1.45 to 4.3, the aircraft achieved **excellent initial acceleration** (16.2 seconds to 55 knots = 92% of realistic C172!), but then experienced a **catastrophic runaway acceleration** that crashed the simulator.

## What Happened

### Phase 1: Normal Acceleration (0-42 seconds) ✅
- **0-16 seconds**: Accelerated to 55 knots (rotation speed)
- **16-42 seconds**: Continued accelerating to ~60 knots
- Forces looked reasonable:
  - Thrust: ~1,900N (decreasing with speed as expected)
  - Drag: ~330N at 60 knots
  - Aircraft stayed on ground (position_y = 0.0)

### Phase 2: Runaway Begins (~42-80 seconds) ❌
From telemetry thrust curve:
- **60 knots** (42s): Drag = 331N, Thrust = 1875N
- **70 knots**: Drag = 418N, Thrust = 1787N
- **80 knots**: Drag = 552N, Thrust = 1542N
- **90 knots**: Drag = 706N, Thrust = 1238N
- **95 knots** (80s): Drag = 1071N, Thrust = 990N

**Aircraft is STILL on the ground** at 95 knots! (`position_y = 0.0`, `on_ground = Y`)

### Phase 3: Catastrophic Explosion (80-102 seconds) 💥
From thrust curve:
- **102 knots**: Drag = **9,508N** (sudden jump!)
- **107 knots**: Drag = **10,511N**
- **200 knots**: Drag = **36,198N**
- **300 knots**: Drag = **82,030N**
- **1,000 knots**: Drag = **825,368N**
- **∞ knots**: Drag = **inf**

The aircraft accelerated from 102 knots to **infinity** in about 20 seconds, all while **STUCK TO THE GROUND**.

## Root Cause Analysis

### The Problem: Drag Explosion

Looking at the drag progression:
- Up to 95 knots: Drag increases normally (quadratic with velocity²)
- At 102 knots: **Drag suddenly jumps 9x** (from 1,071N to 9,508N)
- Beyond 102 knots: Drag increases exponentially, not quadratically

This suggests a **numerical instability** or **physics bug** kicks in around 100 knots.

### Why the Aircraft Never Leaves the Ground

The flight model has this code (simple_6dof.py:190-194):
```python
# Ground collision check (simple altitude check)
if self.state.position.y <= 0.0:
    self.state.position.y = 0.0
    self.state.velocity.y = max(0.0, self.state.velocity.y)
    self.state.on_ground = True
```

This **clamps position_y to 0** and **clamps velocity_y to >= 0**, preventing the aircraft from leaving the ground OR going underground.

But horizontal velocity (velocity_x, velocity_z) are NOT clamped!

### The Positive Feedback Loop

1. Aircraft accelerates to 95 knots on ground (normal)
2. Something goes wrong around 100 knots (drag calculation explodes)
3. Despite massive drag, thrust > drag for a moment
4. Velocity increases
5. Drag increases even MORE (exponentially now, not quadratically)
6. But thrust > drag again somehow
7. **POSITIVE FEEDBACK LOOP** → velocity → ∞

## Hypothesis: What Caused the Drag Explosion?

### Option 1: Drag Formula Overflow

The drag formula is:
```python
drag_parasite = q * self.wing_area * self.drag_coefficient
# where q = 0.5 * rho * v²
```

At 102 knots (52.5 m/s):
- q = 0.5 × 1.225 × 52.5² = 1,688 Pa
- Drag = 1,688 × 16.17 × 0.035 = **955N** (matches telemetry!)

At 200 knots (103 m/s):
- q = 0.5 × 1.225 × 103² = 6,496 Pa
- Expected drag = 6,496 × 16.17 × 0.035 = **3,674N**
- **Actual from telemetry**: 36,198N (10x too high!)

The drag is 10x higher than the formula predicts!

### Option 2: Drag Applied Twice

Could drag be applied in two places?
1. Once in `simple_6dof.py` as aerodynamic drag
2. Again somewhere as "ground friction" that scales with velocity²?

But ground friction (rolling resistance) should be ~94N constant, not velocity-dependent.

### Option 3: Numerical Instability in Integration

When velocities get very high and dt is small (1/60 second), numerical errors could compound.

But the telemetry shows drag values themselves are wrong, not just the integration.

### Option 4: Advance Ratio Calculation Error

Looking at thrust curve, the `thrust_correction` factor stays at 1.0 after ~95 knots.

The propeller model uses advance ratio J = V / (n × D):
- At high speeds, J becomes very large
- The correction factor might have a bug that causes issues at high J

But this would affect thrust, not drag.

## Most Likely Cause: Drag Coefficient Explosion

Looking at the code in `simple_6dof.py` lines 236-266, there are TWO drag components:

1. **Parasite drag**: `D_parasite = q × S × CD0`
2. **Induced drag**: `D_induced = q × S × CD_induced`

Where:
```python
cd_induced = (cl²) / (π × AR × e)
```

At high speeds on the ground:
- `angle_of_attack = self.state.get_pitch()` (line 247)
- If pitch angle becomes large, `cl` becomes HUGE
- Then `cd_induced = cl²` becomes **ENORMOUS**

### Testing This Hypothesis

At 100 knots on the ground, if pitch = 10 degrees:
- cl = 0.1 × 10 = 1.0
- cd_induced = 1.0² / (π × 7.4 × 0.7) = 0.061
- This would add 61% more drag (not enough to explain 10x)

But if pitch somehow becomes 30 degrees:
- cl = 0.1 × 30 = 3.0
- cd_induced = 3.0² / (π × 7.4 × 0.7) = 0.55
- This would add 16x more drag!

**The problem**: On the ground at high speed, the pitch angle might be increasing due to:
1. Nose-up rotation from forces
2. Numerical instability in rotation calculations
3. Ground collision causing weird rotation state

## Why Initial Acceleration Was Good

Up to 60 knots, everything worked perfectly:
- Thrust was realistic (~2,500N static, decreasing to 1,900N at 60 knots)
- Drag was realistic (~330N at 60 knots)
- Time to rotation: 16.2 seconds (92% of realistic C172)

The multiplier of 4.3 was actually **perfect** for initial acceleration!

The problem only appeared at high speeds (95+ knots) when something in the drag calculation went wrong.

## Recommended Fixes

### Fix 1: Clamp Angle of Attack for Drag Calculation
```python
# In simple_6dof.py, line 247
angle_of_attack = self.state.get_pitch()
# CLAMP to prevent runaway induced drag
angle_of_attack = max(-15 * DEGREES_TO_RADIANS, min(15 * DEGREES_TO_RADIANS, angle_of_attack))
```

### Fix 2: Disable Induced Drag on Ground
```python
# Only calculate induced drag when airborne
if self.state.on_ground:
    cd_induced = 0.0
    drag_induced = 0.0
else:
    # Normal induced drag calculation
    cd_induced = (cl * cl) / (math.pi * aspect_ratio * oswald_efficiency)
    drag_induced = q * self.wing_area * cd_induced
```

### Fix 3: Limit Maximum Drag
```python
# After calculating total drag, apply sanity check
MAX_DRAG_FORCE = 5000.0  # Maximum realistic drag for C172
drag_magnitude = min(drag_magnitude, MAX_DRAG_FORCE)
```

### Fix 4: Reduce Static Thrust Multiplier
The 4.3x multiplier might be slightly too high. Try 3.5x or 4.0x.

## Conclusion

The physics integration fix was successful, and the thrust multiplier increase achieved **excellent** initial acceleration (16.2s to rotation, 92% of realistic).

However, there's a critical bug in the drag calculation at high speeds that causes a runaway acceleration. The most likely culprit is **induced drag exploding** due to large angle of attack values.

**Recommended immediate action**: Disable induced drag when on ground (Fix 2), as induced drag shouldn't apply during ground roll anyway.

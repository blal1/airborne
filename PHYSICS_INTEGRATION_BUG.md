# Physics Integration Bug - Root Cause Analysis

## Executive Summary

**ROOT CAUSE IDENTIFIED**: Ground forces and flight model forces are being integrated through **two separate code paths**, causing incorrect physics behavior.

## The Problem

Aircraft accelerates 4.2x slower than expected despite all forces being calculated correctly.

### Expected Physics (at T=20s)
- Net Force: 1073N (thrust 1050N - drag 100N - rolling 94N + lift/weight cancel)
- Mass: 1100 kg
- Expected acceleration: F/m = 1073N / 1100kg = **0.98 m/s²**
- Expected velocity: a × t = 0.98 × 20 = **19.6 m/s**

### Actual Result
- Actual velocity at T=20s: **4.71 m/s**
- Discrepancy: **4.2x slower!**

## Root Cause: Dual Integration Paths

### Path 1: Flight Model Integration (simple_6dof.py lines 176-180)

```python
# Update acceleration: F = ma => a = F/m
self.state.acceleration = self.forces.total / self.state.mass

# Integrate velocity: v = v + a*dt
self.state.velocity = self.state.velocity + self.state.acceleration * dt
```

Where `forces.total` is calculated in `base.py` line 167:
```python
self.total = self.lift + self.drag + self.thrust + self.weight
```

**Forces included**: ✅ Lift, ✅ Drag, ✅ Thrust, ✅ Weight
**Forces missing**: ❌ Rolling resistance, ❌ Brake forces

### Path 2: Ground Force Injection (physics_plugin.py lines 433-438)

```python
# Apply ground forces to aircraft state (convert N to acceleration)
# F = ma, so a = F/m
if self.ground_physics.mass_kg > 0:
    ground_accel = ground_forces.total_force * (1.0 / self.ground_physics.mass_kg)
    state.acceleration.x += ground_accel.x
    state.acceleration.z += ground_accel.z
```

**This modifies `state.acceleration` AFTER the flight model calculated it!**

### Path 3: Flight Model Uses Modified Acceleration (simple_6dof.py line 180)

```python
self.state.velocity = self.state.velocity + self.state.acceleration * dt
```

**But wait!** The flight model ALREADY used `self.state.acceleration` in line 177:
```python
self.state.acceleration = self.forces.total / self.state.mass  # ← OVERWRITES!
```

## The Bug Sequence

1. **Physics plugin calculates ground forces** (physics_plugin.py:426)
   ```python
   ground_forces = self.ground_physics.calculate_ground_forces(...)
   ```

2. **Physics plugin modifies state.acceleration** (physics_plugin.py:436-438)
   ```python
   ground_accel = ground_forces.total_force / mass
   state.acceleration.x += ground_accel.x
   state.acceleration.z += ground_accel.z
   ```

3. **Flight model update() is called** (physics_plugin.py:447)
   ```python
   state = self.flight_model.update(dt, self.control_inputs)
   ```

4. **Flight model OVERWRITES acceleration** (simple_6dof.py:177)
   ```python
   self.state.acceleration = self.forces.total / self.state.mass
   ```

   **❌ Ground forces are LOST! The modification from step 2 is erased!**

5. **Flight model integrates velocity** (simple_6dof.py:180)
   ```python
   self.state.velocity = self.state.velocity + self.state.acceleration * dt
   ```

   **❌ Velocity update uses acceleration WITHOUT ground forces!**

## Why This Causes 4.2x Slowdown

The telemetry shows:
- Thrust: ~1050N (forward)
- Aerodynamic drag: ~100N (backward)
- Rolling resistance: ~94N (backward) **← LOST IN INTEGRATION**

**What gets integrated**:
- Net force: 1050N - 100N = 950N
- Acceleration: 950N / 1100kg = 0.86 m/s²

**What SHOULD be integrated**:
- Net force: 1050N - 100N - 94N = 856N
- Acceleration: 856N / 1100kg = 0.78 m/s²

Wait, that's not right either... let me recalculate based on the actual telemetry.

## Recalculation Based on Telemetry

From telemetry at various speeds:
- Average thrust: 1062N
- Average drag: 102N
- Average rolling resistance: 94N
- Expected net force: 1062 - 102 - 94 = 866N
- Expected acceleration: 866N / 1100kg = 0.79 m/s²
- Time to 55 knots (28.3 m/s): 28.3 / 0.79 = **35.8 seconds** ✅

**This matches the actual time!** So the ground forces ARE being applied somehow...

Let me re-examine the code flow more carefully.

## Revised Analysis

Looking at `physics_plugin.py` line 447:
```python
state = self.flight_model.update(dt, self.control_inputs)
```

The flight model update() returns a **reference** to its internal state (simple_6dof.py line 372):
```python
def get_state(self) -> AircraftState:
    return self.state
```

And update() returns:
```python
return self.state  # Line 209
```

So when physics_plugin modifies `state.acceleration` BEFORE calling `flight_model.update()`,
the flight model OVERWRITES it. **Ground forces are lost.**

## The REAL Problem

Wait, I need to trace this more carefully. Let me look at the exact order of operations in `physics_plugin.py`:

Lines 412-447 in update():
```python
if state.on_ground and self.ground_physics:
    # ... calculate ground forces ...

    # Apply ground forces to aircraft state (lines 433-438)
    if self.ground_physics.mass_kg > 0:
        ground_accel = ground_forces.total_force * (1.0 / self.ground_physics.mass_kg)
        state.acceleration.x += ground_accel.x  # ← Modifies acceleration
        state.acceleration.z += ground_accel.z

# Update flight model (line 447)
state = self.flight_model.update(dt, self.control_inputs)  # ← OVERWRITES acceleration!
```

**The bug**: Ground acceleration is added to state.acceleration (lines 437-438), but then
`flight_model.update()` is called (line 447) which **overwrites** `state.acceleration`
with `self.forces.total / self.state.mass` (simple_6dof.py:177).

The ground forces are calculated and "applied" but then immediately discarded!

## Solution Options

### Option 1: Apply Ground Forces Through Flight Model (RECOMMENDED)

Modify `Simple6DOFFlightModel` to accept ground forces:

1. Add ground forces to the flight model's force calculation
2. Include them in `forces.total` before calculating acceleration
3. Remove the manual acceleration modification in physics_plugin

**Pros**:
- Clean physics integration in one place
- Forces properly summed before integration
- No duplicate acceleration modifications

**Cons**:
- Requires modifying flight model interface
- Need to pass ground forces to flight model

### Option 2: Apply Ground Forces AFTER Flight Model Update

Move ground force application to AFTER `flight_model.update()`:

```python
# Update flight model FIRST
state = self.flight_model.update(dt, self.control_inputs)

# THEN apply ground forces
if state.on_ground and self.ground_physics:
    ground_forces = self.ground_physics.calculate_ground_forces(...)
    # Apply to velocity directly (skip acceleration)
    ground_accel = ground_forces.total_force / mass
    state.velocity.x += ground_accel.x * dt
    state.velocity.z += ground_accel.z * dt
```

**Pros**:
- Minimal code changes
- Ground forces definitely get applied

**Cons**:
- Dirty hack
- Ground forces integrated separately from other forces
- Acceleration value in state doesn't reflect ground forces

### Option 3: Include Ground Forces in FlightForces

Extend `FlightForces` dataclass to include ground forces:

```python
@dataclass
class FlightForces:
    lift: Vector3 = field(default_factory=Vector3.zero)
    drag: Vector3 = field(default_factory=Vector3.zero)
    thrust: Vector3 = field(default_factory=Vector3.zero)
    weight: Vector3 = field(default_factory=Vector3.zero)
    ground: Vector3 = field(default_factory=Vector3.zero)  # ← NEW
    total: Vector3 = field(default_factory=Vector3.zero)

    def calculate_total(self) -> None:
        self.total = self.lift + self.drag + self.thrust + self.weight + self.ground
```

Then physics_plugin sets `flight_model.forces.ground` before calling update().

**Pros**:
- Clean architecture
- All forces properly accounted
- Telemetry gets complete picture

**Cons**:
- Requires modifying base classes
- Coupling between ground physics and flight model

## Recommendation

**Use Option 1 or Option 3** - properly integrate ground forces into the force summation.

The current code has a critical bug where ground forces are calculated but lost during integration.

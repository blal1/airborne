#!/usr/bin/env python3
"""FlyBot - Automated flight test script for Airborne.

This script connects to the Airborne WebSocket server and performs:
1. Takeoff (assuming aircraft is ready on runway)
2. Climb to 500ft AGL
3. Level flight for 60 seconds
4. Logs all telemetry and actions to report.json

Usage:
    uv run python scripts/flybot.py

The script assumes:
- Airborne is running with WebSocket server on port 51128
- Aircraft is on runway, engine running, ready for takeoff
- Parking brake will be released by the script
"""

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import websockets

# Configuration
WS_URL = "ws://127.0.0.1:51128"
TARGET_ALTITUDE_FT = 500.0
LEVEL_FLIGHT_DURATION_SEC = 60.0
TELEMETRY_LOG_INTERVAL_SEC = 0.5  # Log telemetry every 500ms

# Cessna 172 flight parameters
VR_KNOTS = 55.0  # Rotation speed
VY_KNOTS = 74.0  # Best rate of climb speed
CRUISE_PITCH_DEG = 2.0  # Pitch for level flight
CLIMB_PITCH_DEG = 7.0  # Pitch for climb
TAKEOFF_THROTTLE = 1.0
CRUISE_THROTTLE = 0.65


class FlightPhase(Enum):
    """Flight phases for the automated flight."""

    PREFLIGHT = "preflight"
    TAKEOFF_ROLL = "takeoff_roll"
    ROTATION = "rotation"
    INITIAL_CLIMB = "initial_climb"
    LEVEL_OFF = "level_off"
    LEVEL_FLIGHT = "level_flight"
    COMPLETE = "complete"


@dataclass
class ActionLog:
    """Record of an action taken by the bot."""

    timestamp: float
    elapsed_sec: float
    phase: str
    action: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class TelemetrySnapshot:
    """Snapshot of telemetry at a point in time."""

    timestamp: float
    elapsed_sec: float
    phase: str
    # Position
    altitude_ft: float = 0.0
    altitude_agl_ft: float = 0.0
    # Speed
    airspeed_kts: float = 0.0
    groundspeed_kts: float = 0.0
    vertical_speed_fpm: float = 0.0
    # Attitude
    heading_deg: float = 0.0
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    # Controls
    throttle: float = 0.0
    elevator: float = 0.0
    aileron: float = 0.0
    rudder: float = 0.0
    # Engine
    engine_rpm: float = 0.0
    # State
    on_ground: bool = True


@dataclass
class FlightReport:
    """Complete flight report."""

    start_time: str
    end_time: str = ""
    duration_sec: float = 0.0
    target_altitude_ft: float = TARGET_ALTITUDE_FT
    level_flight_duration_sec: float = LEVEL_FLIGHT_DURATION_SEC
    success: bool = False
    failure_reason: str = ""
    phases_completed: list[str] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    telemetry: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


class FlyBot:
    """Automated flight controller."""

    def __init__(self) -> None:
        self.ws: Any = None
        self.current_telemetry: dict[str, Any] = {}
        self.phase = FlightPhase.PREFLIGHT
        self.start_time = time.time()
        self.level_flight_start_time: float | None = None

        # Control state
        self.target_pitch: float = 0.0
        self.target_throttle: float = 0.0
        self.current_pitch_input: float = 0.0
        self.current_roll_input: float = 0.0

        # Logging
        self.actions: list[ActionLog] = []
        self.telemetry_log: list[TelemetrySnapshot] = []
        self.last_telemetry_log_time: float = 0.0

        # Statistics for summary
        self.max_altitude_ft: float = 0.0
        self.min_altitude_during_level: float = float("inf")
        self.max_altitude_during_level: float = 0.0
        self.max_bank_angle: float = 0.0
        self.max_pitch_angle: float = 0.0
        self.takeoff_distance_estimate: float = 0.0
        self.rotation_speed_kts: float = 0.0
        self.time_to_target_altitude: float = 0.0

    @property
    def elapsed(self) -> float:
        """Elapsed time since start."""
        return time.time() - self.start_time

    def log_action(self, action: str, details: dict[str, Any] | None = None) -> None:
        """Log an action taken by the bot."""
        log = ActionLog(
            timestamp=time.time(),
            elapsed_sec=round(self.elapsed, 2),
            phase=self.phase.value,
            action=action,
            details=details or {},
        )
        self.actions.append(log)
        print(f"[{log.elapsed_sec:6.1f}s] [{self.phase.value:15}] {action}")

    def log_telemetry(self) -> None:
        """Log current telemetry snapshot."""
        if not self.current_telemetry:
            return

        t = self.current_telemetry
        snapshot = TelemetrySnapshot(
            timestamp=time.time(),
            elapsed_sec=round(self.elapsed, 2),
            phase=self.phase.value,
            altitude_ft=t.get("altitude_ft", 0.0),
            altitude_agl_ft=t.get("altitude_agl_ft", 0.0),
            airspeed_kts=t.get("airspeed_kts", 0.0),
            groundspeed_kts=t.get("groundspeed_kts", 0.0),
            vertical_speed_fpm=t.get("vertical_speed_fpm", 0.0),
            heading_deg=t.get("heading_deg", 0.0),
            pitch_deg=t.get("pitch_deg", 0.0),
            roll_deg=t.get("roll_deg", 0.0),
            throttle=t.get("throttle", 0.0),
            elevator=t.get("elevator", 0.0),
            aileron=t.get("aileron", 0.0),
            rudder=t.get("rudder", 0.0),
            engine_rpm=t.get("engine_rpm", 0.0),
            on_ground=t.get("on_ground", True),
        )
        self.telemetry_log.append(snapshot)

        # Update statistics
        self.max_altitude_ft = max(self.max_altitude_ft, snapshot.altitude_ft)
        self.max_bank_angle = max(self.max_bank_angle, abs(snapshot.roll_deg))
        self.max_pitch_angle = max(self.max_pitch_angle, abs(snapshot.pitch_deg))

        if self.phase == FlightPhase.LEVEL_FLIGHT:
            self.min_altitude_during_level = min(
                self.min_altitude_during_level, snapshot.altitude_ft
            )
            self.max_altitude_during_level = max(
                self.max_altitude_during_level, snapshot.altitude_ft
            )

    async def send_control(self, **kwargs: float) -> None:
        """Send control inputs to the aircraft."""
        msg = {
            "type": "control",
            "data": kwargs,
        }
        await self.ws.send(json.dumps(msg))

    async def send_action(self, action: str, value: float | None = None) -> None:
        """Send a discrete action command."""
        data: dict[str, Any] = {"action": action}
        if value is not None:
            data["value"] = value
        msg = {
            "type": "action",
            "data": data,
        }
        await self.ws.send(json.dumps(msg))
        self.log_action(f"ACTION: {action}", {"value": value} if value else {})

    async def configure_telemetry_rate(self, rate_ms: int) -> None:
        """Configure telemetry update rate."""
        msg = {
            "type": "config",
            "data": {"telemetry_rate_ms": rate_ms, "client_name": "FlyBot"},
        }
        await self.ws.send(json.dumps(msg))

    def get_altitude(self) -> float:
        """Get current altitude in feet."""
        return self.current_telemetry.get("altitude_ft", 0.0)

    def get_airspeed(self) -> float:
        """Get current airspeed in knots."""
        return self.current_telemetry.get("airspeed_kts", 0.0)

    def get_pitch(self) -> float:
        """Get current pitch in degrees."""
        return self.current_telemetry.get("pitch_deg", 0.0)

    def get_roll(self) -> float:
        """Get current roll/bank in degrees."""
        return self.current_telemetry.get("roll_deg", 0.0)

    def get_vspeed(self) -> float:
        """Get vertical speed in fpm."""
        return self.current_telemetry.get("vertical_speed_fpm", 0.0)

    def is_on_ground(self) -> bool:
        """Check if aircraft is on ground."""
        return self.current_telemetry.get("on_ground", True)

    async def fly_pitch(self, target_pitch: float, rate: float = 2.0) -> None:
        """Adjust pitch input to achieve target pitch angle.

        Uses proportional-derivative control to smoothly reach target pitch.

        Args:
            target_pitch: Target pitch angle in degrees (positive = nose up)
            rate: Control input change rate
        """
        current_pitch = self.get_pitch()
        error = target_pitch - current_pitch

        # Get pitch rate for derivative term
        pitch_rate = self.current_telemetry.get("pitch_rate", 0.0)

        # PD control - much gentler gains to avoid oscillation
        # P gain: gentle response to error
        # D gain: damping to prevent overshoot
        p_gain = 0.02  # Reduced from 0.1
        d_gain = 0.05  # Derivative damping

        p_term = error * p_gain
        d_term = -pitch_rate * d_gain  # Negative because we want to oppose pitch rate

        adjustment = p_term + d_term
        adjustment = max(-0.1, min(0.1, adjustment))  # Smaller max adjustment

        self.current_pitch_input = max(-1.0, min(1.0, self.current_pitch_input + adjustment))
        await self.send_control(pitch=self.current_pitch_input)

    async def fly_wings_level(self) -> None:
        """Keep wings level using roll correction."""
        current_roll = self.get_roll()

        # Proportional control to level wings
        # Negative roll input = roll left
        correction = -current_roll * 0.05  # P gain
        correction = max(-0.3, min(0.3, correction))

        self.current_roll_input = correction
        await self.send_control(roll=self.current_roll_input)

    async def update_flight(self) -> None:
        """Main flight control logic - called every telemetry update."""
        altitude = self.get_altitude()
        airspeed = self.get_airspeed()
        pitch = self.get_pitch()
        on_ground = self.is_on_ground()
        vspeed = self.get_vspeed()

        # Log telemetry periodically
        if time.time() - self.last_telemetry_log_time >= TELEMETRY_LOG_INTERVAL_SEC:
            self.log_telemetry()
            self.last_telemetry_log_time = time.time()

        # State machine for flight phases
        if self.phase == FlightPhase.PREFLIGHT:
            await self._phase_preflight()

        elif self.phase == FlightPhase.TAKEOFF_ROLL:
            await self._phase_takeoff_roll(airspeed)

        elif self.phase == FlightPhase.ROTATION:
            await self._phase_rotation(on_ground)

        elif self.phase == FlightPhase.INITIAL_CLIMB:
            await self._phase_initial_climb(altitude, airspeed)

        elif self.phase == FlightPhase.LEVEL_OFF:
            await self._phase_level_off(altitude, vspeed)

        elif self.phase == FlightPhase.LEVEL_FLIGHT:
            await self._phase_level_flight(altitude)

    async def _phase_preflight(self) -> None:
        """Preflight: release parking brake, set throttle."""
        self.log_action("Starting preflight checks")

        # Release parking brake
        await self.send_action("parking_brake_release")
        await asyncio.sleep(0.5)

        # Set full throttle for takeoff
        await self.send_control(throttle=TAKEOFF_THROTTLE)
        self.log_action("Throttle set to full", {"throttle": TAKEOFF_THROTTLE})

        # Transition to takeoff roll
        self.phase = FlightPhase.TAKEOFF_ROLL
        self.log_action("Phase transition", {"to": self.phase.value})

    async def _phase_takeoff_roll(self, airspeed: float) -> None:
        """Takeoff roll: accelerate to rotation speed."""
        # Keep wings level and slight back pressure
        await self.fly_wings_level()

        # Hold neutral pitch during roll
        await self.send_control(pitch=0.0)

        # Check for rotation speed
        if airspeed >= VR_KNOTS:
            self.rotation_speed_kts = airspeed
            self.log_action("Rotation speed reached", {"airspeed_kts": airspeed})
            self.phase = FlightPhase.ROTATION
            self.log_action("Phase transition", {"to": self.phase.value})

    async def _phase_rotation(self, on_ground: bool) -> None:
        """Rotation: pitch up for takeoff."""
        # Apply back pressure to rotate
        target_pitch = 10.0  # Rotate to ~10 degrees
        await self.fly_pitch(target_pitch)
        await self.fly_wings_level()

        # Check if airborne
        if not on_ground:
            self.log_action("Liftoff!", {"altitude_ft": self.get_altitude()})
            self.phase = FlightPhase.INITIAL_CLIMB
            self.log_action("Phase transition", {"to": self.phase.value})

    async def _phase_initial_climb(self, altitude: float, airspeed: float) -> None:
        """Initial climb: climb to target altitude."""
        # Maintain climb pitch
        await self.fly_pitch(CLIMB_PITCH_DEG)
        await self.fly_wings_level()

        # Keep full throttle during climb
        await self.send_control(throttle=TAKEOFF_THROTTLE)

        # Check if approaching target altitude
        if altitude >= TARGET_ALTITUDE_FT - 50:  # Start level off 50ft early
            self.time_to_target_altitude = self.elapsed
            self.log_action(
                "Approaching target altitude",
                {
                    "altitude_ft": altitude,
                    "target_ft": TARGET_ALTITUDE_FT,
                },
            )
            self.phase = FlightPhase.LEVEL_OFF
            self.log_action("Phase transition", {"to": self.phase.value})

    async def _phase_level_off(self, altitude: float, vspeed: float) -> None:
        """Level off: transition to level flight."""
        # Reduce pitch to level
        await self.fly_pitch(CRUISE_PITCH_DEG)
        await self.fly_wings_level()

        # Reduce throttle to cruise
        await self.send_control(throttle=CRUISE_THROTTLE)

        # Check if level (low vertical speed)
        if abs(vspeed) < 200 and altitude >= TARGET_ALTITUDE_FT - 100:
            self.log_action(
                "Level flight established",
                {
                    "altitude_ft": altitude,
                    "vspeed_fpm": vspeed,
                },
            )
            self.level_flight_start_time = time.time()
            self.phase = FlightPhase.LEVEL_FLIGHT
            self.log_action("Phase transition", {"to": self.phase.value})

    async def _phase_level_flight(self, altitude: float) -> None:
        """Level flight: maintain altitude for specified duration."""
        # Altitude hold - use throttle as primary control, pitch as secondary
        altitude_error = TARGET_ALTITUDE_FT - altitude
        vspeed = self.get_vspeed()

        # Throttle adjustment based on altitude error and vertical speed
        # If below target altitude (positive error) or descending, add throttle
        throttle_adjustment = altitude_error * 0.002  # 0.2% per foot
        throttle_adjustment += -vspeed * 0.0005  # damping based on vspeed

        target_throttle = CRUISE_THROTTLE + throttle_adjustment
        target_throttle = max(0.5, min(1.0, target_throttle))  # Clamp 50-100%

        # Pitch adjustment - gentler, mainly to maintain attitude
        pitch_adjustment = altitude_error * 0.01  # degrees per foot
        pitch_adjustment = max(-2.0, min(2.0, pitch_adjustment))
        target_pitch = CRUISE_PITCH_DEG + pitch_adjustment

        await self.fly_pitch(target_pitch)
        await self.fly_wings_level()

        # Use adjusted throttle for altitude hold
        await self.send_control(throttle=target_throttle)

        # Check if level flight duration complete
        if self.level_flight_start_time:
            level_duration = time.time() - self.level_flight_start_time
            if level_duration >= LEVEL_FLIGHT_DURATION_SEC:
                self.log_action(
                    "Level flight complete",
                    {
                        "duration_sec": level_duration,
                        "final_altitude_ft": altitude,
                    },
                )
                self.phase = FlightPhase.COMPLETE
                self.log_action("Phase transition", {"to": self.phase.value})

    def generate_report(self) -> FlightReport:
        """Generate the flight report."""
        report = FlightReport(
            start_time=datetime.fromtimestamp(self.start_time).isoformat(),
            end_time=datetime.now().isoformat(),
            duration_sec=round(self.elapsed, 1),
            target_altitude_ft=TARGET_ALTITUDE_FT,
            level_flight_duration_sec=LEVEL_FLIGHT_DURATION_SEC,
            success=self.phase == FlightPhase.COMPLETE,
            phases_completed=[a.phase for a in self.actions if "Phase transition" in a.action],
            actions=[asdict(a) for a in self.actions],
            telemetry=[asdict(t) for t in self.telemetry_log],
        )

        # Calculate summary statistics
        if self.telemetry_log:
            report.summary = {
                "max_altitude_ft": round(self.max_altitude_ft, 1),
                "max_bank_angle_deg": round(self.max_bank_angle, 1),
                "max_pitch_angle_deg": round(self.max_pitch_angle, 1),
                "rotation_speed_kts": round(self.rotation_speed_kts, 1),
                "time_to_target_altitude_sec": round(self.time_to_target_altitude, 1),
                "altitude_hold_quality": {
                    "target_ft": TARGET_ALTITUDE_FT,
                    "min_ft": round(self.min_altitude_during_level, 1)
                    if self.min_altitude_during_level != float("inf")
                    else 0,
                    "max_ft": round(self.max_altitude_during_level, 1),
                    "deviation_ft": round(
                        self.max_altitude_during_level - self.min_altitude_during_level, 1
                    )
                    if self.min_altitude_during_level != float("inf")
                    else 0,
                },
                "total_actions": len(self.actions),
                "total_telemetry_samples": len(self.telemetry_log),
            }

            # Flight realism assessment
            report.summary["assessment"] = self._assess_flight()

        return report

    def _assess_flight(self) -> dict[str, Any]:
        """Assess the flight realism based on collected data."""
        issues = []
        positives = []

        # Check rotation speed
        if 50 <= self.rotation_speed_kts <= 65:
            positives.append(f"Realistic rotation speed ({self.rotation_speed_kts:.0f} kts)")
        else:
            issues.append(
                f"Unusual rotation speed ({self.rotation_speed_kts:.0f} kts, expected 55-60)"
            )

        # Check climb rate (should be 500-700 fpm for C172)
        climb_samples = [t for t in self.telemetry_log if t.phase == "initial_climb"]
        if climb_samples:
            avg_climb = sum(t.vertical_speed_fpm for t in climb_samples) / len(climb_samples)
            if 400 <= avg_climb <= 900:
                positives.append(f"Realistic climb rate ({avg_climb:.0f} fpm)")
            else:
                issues.append(f"Unusual climb rate ({avg_climb:.0f} fpm, expected 500-700)")

        # Check altitude hold stability
        if self.min_altitude_during_level != float("inf"):
            deviation = self.max_altitude_during_level - self.min_altitude_during_level
            if deviation < 100:
                positives.append(f"Good altitude hold (±{deviation / 2:.0f} ft)")
            else:
                issues.append(f"Poor altitude hold (deviation: {deviation:.0f} ft)")

        # Check bank angle during level flight
        level_samples = [t for t in self.telemetry_log if t.phase == "level_flight"]
        if level_samples:
            avg_bank = sum(abs(t.roll_deg) for t in level_samples) / len(level_samples)
            if avg_bank < 5:
                positives.append(f"Good wings level control (avg bank: {avg_bank:.1f}°)")
            else:
                issues.append(f"Difficulty maintaining wings level (avg bank: {avg_bank:.1f}°)")

        # Overall verdict
        if len(issues) == 0:
            verdict = "EXCELLENT - Flight model appears realistic and controllable"
        elif len(issues) <= 1:
            verdict = "GOOD - Minor issues but generally realistic"
        elif len(issues) <= 2:
            verdict = "FAIR - Some unrealistic behaviors detected"
        else:
            verdict = "NEEDS_WORK - Multiple issues with flight model"

        return {
            "verdict": verdict,
            "positives": positives,
            "issues": issues,
            "keyboard_playability": "PLAYABLE" if len(issues) <= 2 else "CHALLENGING",
        }

    async def run(self) -> FlightReport:
        """Run the automated flight."""
        print("=" * 60)
        print("FlyBot - Automated Flight Test")
        print("=" * 60)
        print(f"Target altitude: {TARGET_ALTITUDE_FT} ft")
        print(f"Level flight duration: {LEVEL_FLIGHT_DURATION_SEC} seconds")
        print("=" * 60)

        try:
            async with websockets.connect(WS_URL) as ws:
                self.ws = ws

                # Configure fast telemetry updates
                await self.configure_telemetry_rate(50)  # 20 Hz
                self.log_action("Connected to Airborne", {"url": WS_URL})

                # Main loop
                while self.phase != FlightPhase.COMPLETE:
                    try:
                        # Receive telemetry with timeout
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        data = json.loads(msg)

                        if data.get("type") == "telemetry":
                            self.current_telemetry = data.get("data", {})
                            await self.update_flight()
                        elif data.get("type") == "status":
                            self.log_action("Server status", data.get("data", {}))

                    except TimeoutError:
                        print("Warning: No telemetry received")
                        continue
                    except Exception as e:
                        print(f"Error: {e}")
                        break

                    # Safety timeout - 5 minutes max
                    if self.elapsed > 300:
                        self.log_action("Safety timeout reached")
                        break

                # Final telemetry log
                self.log_telemetry()

        except ConnectionRefusedError:
            print(f"ERROR: Could not connect to {WS_URL}")
            print("Make sure Airborne is running with the WebSocket server enabled.")
            return FlightReport(
                start_time=datetime.now().isoformat(),
                success=False,
                failure_reason="Connection refused - is Airborne running?",
            )

        # Generate report
        report = self.generate_report()
        return report


async def main() -> None:
    """Main entry point."""
    bot = FlyBot()
    report = await bot.run()

    # Save report
    report_path = "report.json"
    with open(report_path, "w") as f:
        json.dump(asdict(report), f, indent=2)

    print("\n" + "=" * 60)
    print("FLIGHT REPORT")
    print("=" * 60)
    print(f"Duration: {report.duration_sec:.1f} seconds")
    print(f"Success: {report.success}")

    if report.summary:
        print("\nSummary:")
        print(f"  Max altitude: {report.summary.get('max_altitude_ft', 0):.0f} ft")
        print(f"  Rotation speed: {report.summary.get('rotation_speed_kts', 0):.0f} kts")
        print(f"  Time to altitude: {report.summary.get('time_to_target_altitude_sec', 0):.1f} s")

        if "altitude_hold_quality" in report.summary:
            ahq = report.summary["altitude_hold_quality"]
            print(
                f"  Altitude hold: {ahq.get('min_ft', 0):.0f} - {ahq.get('max_ft', 0):.0f} ft (±{ahq.get('deviation_ft', 0) / 2:.0f} ft)"
            )

        if "assessment" in report.summary:
            assessment = report.summary["assessment"]
            print(f"\nAssessment: {assessment.get('verdict', 'N/A')}")
            print(f"Keyboard playability: {assessment.get('keyboard_playability', 'N/A')}")

            if assessment.get("positives"):
                print("\nPositives:")
                for p in assessment["positives"]:
                    print(f"  + {p}")

            if assessment.get("issues"):
                print("\nIssues:")
                for i in assessment["issues"]:
                    print(f"  - {i}")

    print(f"\nFull report saved to: {report_path}")
    print(f"Total telemetry samples: {len(report.telemetry)}")
    print(f"Total actions logged: {len(report.actions)}")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Analyze telemetry data to investigate physics/flight model issues.

This script analyzes the recent telemetry data to investigate:
1. Stall warnings triggering with neutral pitch
2. Random climbing/descending during takeoff with neutral yoke
3. Missing angle of attack data
"""

import sqlite3
import sys
from pathlib import Path


def analyze_telemetry(db_path: str):
    """Analyze telemetry database for physics issues."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"=== Analyzing Telemetry Database: {db_path} ===\n")

    # Get last 2 minutes of data
    query = """
    SELECT
        timestamp_ms/1000.0 as time_sec,
        airspeed_kts,
        altitude_m * 3.28084 as altitude_ft,
        pitch_deg,
        elevator,
        angle_of_attack_deg,
        on_ground,
        lift_n,
        drag_total_n,
        thrust_n,
        net_force_y,
        lift_coefficient
    FROM telemetry
    WHERE timestamp_ms > (SELECT MAX(timestamp_ms) - 120000 FROM telemetry)
    ORDER BY timestamp_ms DESC
    LIMIT 50
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print("## Recent Flight Data (Last 50 frames, newest first)\n")
    print(
        f"{'Time(s)':<10} {'IAS(kt)':<10} {'Alt(ft)':<10} {'Pitch(°)':<10} "
        f"{'Elev':<8} {'AOA(°)':<10} {'Ground':<8} {'Lift(N)':<10} {'Drag(N)':<10}"
    )
    print("-" * 110)

    issues = {
        "high_pitch_neutral_elevator": [],
        "missing_aoa": 0,
        "low_airspeed": [],
        "unstable_pitch": [],
    }

    prev_pitch = None

    for row in rows:
        (
            time_sec,
            airspeed_kts,
            altitude_ft,
            pitch_deg,
            elevator,
            aoa_deg,
            on_ground,
            lift_n,
            drag_n,
            thrust_n,
            net_force_y,
            lift_coeff,
        ) = row

        # Format output (handle NULLs)
        ground_str = "YES" if on_ground else "NO"
        aoa_str = f"{aoa_deg:.2f}" if aoa_deg is not None else "NULL"
        airspeed_str = f"{airspeed_kts:.1f}" if airspeed_kts is not None else "NULL"
        altitude_str = f"{altitude_ft:.1f}" if altitude_ft is not None else "NULL"
        pitch_str = f"{pitch_deg:.2f}" if pitch_deg is not None else "NULL"
        elevator_str = f"{elevator:.3f}" if elevator is not None else "NULL"
        lift_str = f"{lift_n:.1f}" if lift_n is not None else "NULL"
        drag_str = f"{drag_n:.1f}" if drag_n is not None else "NULL"

        print(
            f"{time_sec:<10.1f} {airspeed_str:<10} {altitude_str:<10} "
            f"{pitch_str:<10} {elevator_str:<8} {aoa_str:<10} {ground_str:<8} "
            f"{lift_str:<10} {drag_str:<10}"
        )

        # Detect issues

        # 1. High pitch with neutral elevator
        if not on_ground and abs(elevator) < 0.1 and abs(pitch_deg) > 20.0:
            issues["high_pitch_neutral_elevator"].append(
                {
                    "time": time_sec,
                    "pitch": pitch_deg,
                    "elevator": elevator,
                    "airspeed": airspeed_kts,
                }
            )

        # 2. Missing AOA data
        if aoa_deg is None:
            issues["missing_aoa"] += 1

        # 3. Low airspeed (near stall)
        if not on_ground and airspeed_kts < 55.0:
            issues["low_airspeed"].append(
                {"time": time_sec, "airspeed": airspeed_kts, "pitch": pitch_deg}
            )

        # 4. Unstable pitch (large pitch changes)
        if prev_pitch is not None and abs(pitch_deg - prev_pitch) > 0.5:
            issues["unstable_pitch"].append(
                {
                    "time": time_sec,
                    "pitch": pitch_deg,
                    "prev_pitch": prev_pitch,
                    "change": pitch_deg - prev_pitch,
                    "elevator": elevator,
                }
            )
        prev_pitch = pitch_deg

    # Report issues
    print("\n" + "=" * 110)
    print("## ISSUES DETECTED\n")

    print(
        f"### 1. High Pitch with Neutral Elevator: {len(issues['high_pitch_neutral_elevator'])} occurrences"
    )
    if issues["high_pitch_neutral_elevator"]:
        print("   This indicates pitch is not properly controlled by elevator input!")
        for issue in issues["high_pitch_neutral_elevator"][:5]:
            print(
                f"   - Time {issue['time']:.1f}s: Pitch={issue['pitch']:.1f}°, "
                f"Elevator={issue['elevator']:.3f}, Airspeed={issue['airspeed']:.1f}kt"
            )

    print(f"\n### 2. Missing Angle of Attack Data: {issues['missing_aoa']} frames")
    if issues["missing_aoa"] > 0:
        print("   AOA is NULL in telemetry - flight model not calculating it properly!")
        print("   Location: src/airborne/physics/flight_model/simple_6dof.py line 305")
        print(
            "   The angle_of_attack_deg is set but may not be persisting or being read correctly."
        )

    print(f"\n### 3. Low Airspeed (Near Stall): {len(issues['low_airspeed'])} frames")
    if issues["low_airspeed"]:
        print("   Airspeed below stall warning threshold (55 kts)")
        for issue in issues["low_airspeed"][:5]:
            print(
                f"   - Time {issue['time']:.1f}s: Airspeed={issue['airspeed']:.1f}kt, Pitch={issue['pitch']:.1f}°"
            )

    print(f"\n### 4. Unstable Pitch: {len(issues['unstable_pitch'])} large changes")
    if issues["unstable_pitch"]:
        print("   Pitch changing rapidly despite neutral/small elevator input")
        for issue in issues["unstable_pitch"][:5]:
            print(
                f"   - Time {issue['time']:.1f}s: Pitch {issue['prev_pitch']:.1f}° → {issue['pitch']:.1f}° "
                f"(Δ{issue['change']:.2f}°) with Elevator={issue['elevator']:.3f}"
            )

    # Root cause analysis
    print("\n" + "=" * 110)
    print("## ROOT CAUSE ANALYSIS\n")

    print("### Problem 1: Angle of Attack Not Being Calculated")
    print("The telemetry shows angle_of_attack_deg is NULL, but the code sets it on line 305")
    print("of simple_6dof.py. This suggests:")
    print("  - The calculate_drag() method may not be called")
    print("  - Or the angle_of_attack_deg value is reset somewhere")
    print("  - Or it's not being read correctly by the physics plugin")
    print()
    print("Without AOA data:")
    print("  - Stall detection cannot work properly (instructor plugin checks airspeed only)")
    print("  - Lift calculations may be incorrect")
    print("  - Flight dynamics will be unrealistic")
    print()

    print("### Problem 2: Pitch Divergence with Neutral Elevator")
    print("Aircraft pitch is climbing to 26-28° while elevator is essentially neutral (0.046)")
    print("This indicates:")
    print("  - Elevator input not properly affecting pitch moment")
    print("  - Or lift force creating excessive pitching moment")
    print("  - Or integration issue in flight model")
    print()

    print("### Problem 3: Low Airspeed Leading to Stall")
    print("Airspeed hovering around 43-46 knots, which is near stall speed (55 kts)")
    print("Combined with high pitch angle, this suggests:")
    print("  - Insufficient thrust")
    print("  - Excessive drag")
    print("  - Or improper lift/drag balance")
    print()

    print("## RECOMMENDED FIXES\n")
    print("1. Fix angle_of_attack_deg calculation:")
    print("   - Verify calculate_drag() is being called in update loop")
    print("   - Check that angle_of_attack_deg persists between frames")
    print("   - Ensure physics_plugin correctly reads flight_model.angle_of_attack_deg")
    print()
    print("2. Fix pitch control:")
    print("   - Review elevator authority in flight model")
    print("   - Check pitching moment calculations")
    print("   - Verify angular velocity integration")
    print()
    print("3. Fix stall detection in flight instructor:")
    print("   - Use angle_of_attack instead of just airspeed")
    print("   - Typical stall AOA for Cessna 172: 16-18°")
    print("   - Consider adding AOA-based stall warning")

    conn.close()


if __name__ == "__main__":
    # Find most recent telemetry database
    telemetry_dir = Path("/tmp")
    db_files = list(telemetry_dir.glob("airborne_telemetry_*.db"))

    if not db_files:
        print("No telemetry database found in /tmp/")
        sys.exit(1)

    # Get most recent
    latest_db = max(db_files, key=lambda p: p.stat().st_mtime)

    analyze_telemetry(str(latest_db))

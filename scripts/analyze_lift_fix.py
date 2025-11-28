#!/usr/bin/env python3
"""Analyze telemetry after lift direction fix."""

import sqlite3
import sys


def analyze_lift_fix(db_path: str):
    """Analyze telemetry to check if lift fix resolved the runaway."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 80)
    print("LIFT FIX ANALYSIS")
    print("=" * 80)

    # Get overall stats
    cursor.execute("""
        SELECT
            COUNT(*) as frames,
            MAX(timestamp_ms)/1000.0 as duration_sec,
            MAX(airspeed_kts) as max_speed,
            MAX(position_y) as max_altitude,
            MAX(velocity_y) as max_climb_rate
        FROM telemetry
    """)

    stats = cursor.fetchone()
    print(f"\nTest Duration: {stats[1]:.1f} seconds ({stats[0]} frames)")
    print(f"Max Airspeed: {stats[2]:.1f} knots")
    print(f"Max Altitude: {stats[3]:.1f} meters ({stats[3] * 3.28084:.0f} feet)")
    print(f"Max Climb Rate: {stats[4]:.1f} m/s ({stats[4] * 196.85:.0f} ft/min)")

    # Check for runaway acceleration (> 150 knots)
    cursor.execute("""
        SELECT COUNT(*) FROM telemetry WHERE airspeed_kts > 150
    """)
    runaway_count = cursor.fetchone()[0]

    if runaway_count > 0:
        print(f"\n❌ RUNAWAY DETECTED: {runaway_count} frames > 150 knots")
    else:
        print("\n✅ NO RUNAWAY: Airspeed stayed below 150 knots")

    # Speed profile over time
    print("\n\nSPEED AND ALTITUDE PROFILE (every 10 seconds):")
    print("-" * 80)
    print(
        f"{'Time':>6s} {'Speed':>8s} {'Alt_m':>8s} {'Alt_ft':>8s} {'ClimbRate':>10s} {'OnGround':>9s}"
    )
    print("-" * 80)

    cursor.execute("""
        SELECT
            timestamp_ms/1000.0 as time,
            airspeed_kts,
            position_y,
            velocity_y,
            on_ground
        FROM telemetry
        WHERE CAST(timestamp_ms/1000 AS INTEGER) % 10 = 0
        ORDER BY timestamp_ms
        LIMIT 20
    """)

    for row in cursor.fetchall():
        time_sec = row[0]
        speed = row[1] if row[1] is not None else 0.0
        alt_m = row[2] if row[2] is not None else 0.0
        alt_ft = alt_m * 3.28084
        climb = row[3] if row[3] is not None else 0.0
        on_ground = "Yes" if row[4] else "No"

        print(
            f"{time_sec:6.0f} {speed:8.1f} {alt_m:8.1f} {alt_ft:8.0f} {climb:10.1f} {on_ground:>9s}"
        )

    # Check takeoff performance
    print("\n\nTAKEOFF ANALYSIS:")
    print("-" * 80)

    cursor.execute("""
        SELECT
            MIN(timestamp_ms/1000.0) as liftoff_time,
            airspeed_kts as liftoff_speed
        FROM telemetry
        WHERE on_ground = 0 AND airspeed_kts > 40
        LIMIT 1
    """)

    liftoff = cursor.fetchone()
    if liftoff and liftoff[0]:
        print(f"Liftoff Time: {liftoff[0]:.1f} seconds")
        print(f"Liftoff Speed: {liftoff[1]:.1f} knots")
    else:
        print("Aircraft did not become airborne (on_ground never became 0)")

    # Check lift forces if available
    cursor.execute("SELECT COUNT(*) FROM forces")
    force_count = cursor.fetchone()[0]

    if force_count > 0:
        print(f"\n\nFORCE ANALYSIS ({force_count} force records):")
        print("-" * 80)

        cursor.execute("""
            SELECT
                AVG(lift_y) as avg_lift,
                MAX(lift_y) as max_lift,
                AVG(weight_y) as avg_weight,
                MAX(total_y) as max_net_y,
                MAX(accel_from_forces_y) as max_accel_y
            FROM forces
        """)

        forces = cursor.fetchone()
        print(f"Average Lift: {forces[0]:.0f}N")
        print(f"Maximum Lift: {forces[1]:.0f}N")
        print(f"Average Weight: {forces[2]:.0f}N")
        print(f"Max Net Y Force: {forces[3]:.0f}N")
        print(f"Max Y Acceleration: {forces[4]:.2f} m/s² ({forces[4] / 9.81:.2f} G's)")

        # Check if lift was excessive
        if forces[1] > 30000:
            print(f"\n❌ EXCESSIVE LIFT: Max lift {forces[1]:.0f}N is unrealistic!")
        else:
            print(f"\n✅ LIFT REASONABLE: Max lift {forces[1]:.0f}N is within normal range")

    # Summary
    print("\n\n" + "=" * 80)
    print("VERDICT:")
    print("=" * 80)

    if runaway_count > 0:
        print("❌ LIFT FIX DID NOT RESOLVE RUNAWAY ACCELERATION")
    elif stats[2] < 100:
        print("✅ LIFT FIX APPEARS TO WORK - No runaway acceleration detected")
        print(f"   Max speed {stats[2]:.1f} knots is reasonable")
    else:
        print("⚠️  PARTIAL SUCCESS - Speed higher than expected but no runaway")
        print(f"   Max speed {stats[2]:.1f} knots (expected < 100 knots)")

    conn.close()


if __name__ == "__main__":
    db_path = "/tmp/airborne_telemetry_20251028_165317.db"
    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    analyze_lift_fix(db_path)

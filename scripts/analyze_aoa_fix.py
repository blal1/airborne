#!/usr/bin/env python3
"""Analyze telemetry after AOA clamping and rotational damping fixes."""

import sqlite3
import sys


def analyze_telemetry(db_path):
    """Analyze telemetry data for AOA fixes."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get overall statistics
    cursor.execute("""
        SELECT
            COUNT(*) as total_records,
            MIN(timestamp_ms)/1000.0 as start_time_sec,
            MAX(timestamp_ms)/1000.0 as end_time_sec,
            (MAX(timestamp_ms) - MIN(timestamp_ms))/1000.0 as duration_sec,
            MAX(airspeed_kts) as max_airspeed_kts,
            MAX(angle_of_attack_deg) as max_aoa_deg,
            MAX(altitude_m) as max_altitude_m,
            MAX(drag_induced_n) as max_induced_drag_n,
            MAX(drag_total_n) as max_total_drag_n
        FROM telemetry
    """)
    row = cursor.fetchone()

    print("=" * 80)
    print("AOA FIX ANALYSIS - Telemetry Summary")
    print("=" * 80)
    print(f"Database: {db_path}")
    print(f"Duration: {row[3]:.1f} seconds ({row[0]} records)")
    print(f"Max Airspeed: {row[4] if row[4] is not None else 'N/A'}")
    print(f"Max AOA: {row[5]:.2f}° (limit is 15°)" if row[5] is not None else "Max AOA: N/A")
    print(f"Max Altitude: {row[6]:.2f} m" if row[6] is not None else "Max Altitude: N/A")
    print(f"Max Induced Drag: {row[7]:.0f} N" if row[7] is not None else "Max Induced Drag: N/A")
    print(f"Max Total Drag: {row[8]:.0f} N" if row[8] is not None else "Max Total Drag: N/A")
    print()

    # Check if AOA clamping is working
    if row[5] <= 15.0:
        print("✅ AOA CLAMPING: WORKING - Max AOA is within 15° limit")
    else:
        print(f"❌ AOA CLAMPING: FAILED - Max AOA ({row[5]:.2f}°) exceeds 15° limit")
    print()

    # Find rotation point (when aircraft leaves ground)
    cursor.execute("""
        SELECT
            timestamp_ms/1000.0 as time_sec,
            ROUND(airspeed_kts, 1) as spd_kts,
            on_ground
        FROM telemetry
        WHERE timestamp_ms/1000.0 > 10
        ORDER BY timestamp_ms
        LIMIT 1000
    """)

    last_on_ground_time = None
    first_airborne_time = None
    rotation_speed = None

    for row in cursor.fetchall():
        time_sec, spd_kts, on_ground = row
        if on_ground == 1:
            last_on_ground_time = time_sec
            rotation_speed = spd_kts
        elif on_ground == 0 and last_on_ground_time is not None:
            first_airborne_time = time_sec
            break

    if first_airborne_time:
        print("🛫 ROTATION:")
        print(f"   Last on ground: {last_on_ground_time:.1f}s at {rotation_speed:.1f} knots")
        print(f"   First airborne: {first_airborne_time:.1f}s")
        print()

        # Analyze post-rotation behavior
        cursor.execute(
            """
            SELECT
                timestamp_ms/1000.0 as time_sec,
                ROUND(airspeed_kts, 1) as spd_kts,
                ROUND(angle_of_attack_deg, 2) as aoa_deg,
                ROUND(pitch_deg, 2) as pitch,
                ROUND(drag_parasite_n, 0) as drag_p,
                ROUND(drag_induced_n, 0) as drag_i,
                ROUND(drag_total_n, 0) as drag_tot,
                ROUND(thrust_n, 0) as thrust,
                ROUND(altitude_m, 2) as alt_m
            FROM telemetry
            WHERE timestamp_ms/1000.0 BETWEEN ? AND ? + 10
            ORDER BY timestamp_ms
        """,
            (first_airborne_time, first_airborne_time),
        )

        print("📊 POST-ROTATION ANALYSIS (first 10 seconds airborne):")
        print(
            f"{'Time':>6} {'Spd':>5} {'AOA':>5} {'Pitch':>6} {'D_Para':>7} {'D_Ind':>6} {'D_Tot':>7} {'Thrust':>7} {'Alt':>6}"
        )
        print(
            f"{'(s)':>6} {'(kt)':>5} {'(°)':>5} {'(°)':>6} {'(N)':>7} {'(N)':>6} {'(N)':>7} {'(N)':>7} {'(m)':>6}"
        )
        print("-" * 80)

        for row in cursor.fetchall():
            print(
                f"{row[0]:>6.1f} {row[1]:>5.1f} {row[2]:>5.2f} {row[3]:>6.2f} {row[4]:>7.0f} {row[5]:>6.0f} {row[6]:>7.0f} {row[7]:>7.0f} {row[8]:>6.2f}"
            )

        print()
    else:
        print("⚠️  Aircraft did not become airborne during this session")
        print()

        # Show max speed reached on ground
        cursor.execute("""
            SELECT
                MAX(airspeed_kts) as max_speed,
                MAX(angle_of_attack_deg) as max_aoa,
                MAX(pitch_deg) as max_pitch
            FROM telemetry
            WHERE on_ground = 1
        """)
        row = cursor.fetchone()
        print(f"   Max ground speed: {row[0]:.1f} knots")
        print(f"   Max AOA on ground: {row[1]:.2f}°")
        print(f"   Max pitch on ground: {row[2]:.2f}°")
        print()

    # Check for runaway acceleration
    cursor.execute("""
        SELECT
            timestamp_ms/1000.0 as time_sec,
            ROUND(airspeed_kts, 1) as spd_kts,
            ROUND(drag_total_n, 0) as drag_tot
        FROM telemetry
        WHERE airspeed_kts > 120 OR drag_total_n > 5000
        ORDER BY timestamp_ms
        LIMIT 10
    """)

    runaway_data = cursor.fetchall()
    if runaway_data:
        print("❌ RUNAWAY ACCELERATION DETECTED:")
        print(f"{'Time':>6} {'Speed':>6} {'Drag':>8}")
        print(f"{'(s)':>6} {'(kt)':>6} {'(N)':>8}")
        print("-" * 25)
        for row in runaway_data:
            print(f"{row[0]:>6.1f} {row[1]:>6.1f} {row[2]:>8.0f}")
        print()
    else:
        print("✅ NO RUNAWAY ACCELERATION: No speeds > 120 knots or drag > 5000N")
        print()

    # Summary
    cursor.execute("SELECT MAX(angle_of_attack_deg) FROM telemetry")
    max_aoa = cursor.fetchone()[0]

    print("=" * 80)
    print("CONCLUSION:")
    print("=" * 80)
    if max_aoa <= 15.0:
        print(f"✅ AOA clamping is working correctly (max AOA: {max_aoa:.2f}°)")
    else:
        print(f"❌ AOA clamping failed (max AOA: {max_aoa:.2f}°)")

    if not runaway_data:
        print("✅ No runaway acceleration detected")
    else:
        print("❌ Runaway acceleration still occurring")

    print("=" * 80)

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = "/tmp/airborne_telemetry_20251028_144138.db"

    analyze_telemetry(db_path)

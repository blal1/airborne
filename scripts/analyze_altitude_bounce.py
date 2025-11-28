#!/usr/bin/env python3
"""Analyze altitude bouncing behavior in telemetry."""

import sqlite3
import sys


def analyze_altitude_bounce(db_path: str):
    """Find instances where altitude drops to 0 and rises again."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 80)
    print("ALTITUDE BOUNCE ANALYSIS")
    print("=" * 80)

    # Get altitude profile
    cursor.execute("""
        SELECT
            timestamp_ms/1000.0 as time_sec,
            position_y as altitude_m,
            velocity_y as climb_mps,
            on_ground,
            airspeed_kts
        FROM telemetry
        ORDER BY timestamp_ms
    """)

    data = cursor.fetchall()

    print(f"\nTotal frames: {len(data)}")
    print(f"Duration: {data[-1][0]:.1f} seconds")

    # Find bounce events: altitude goes to 0 after being > 1m, then rises again
    bounces = []
    was_airborne = False
    ground_start = None

    for i, row in enumerate(data):
        time_sec, alt_m, climb_mps, on_ground, speed_kts = row

        if alt_m > 1.0:
            was_airborne = True
            if ground_start is not None:
                # We were on ground, now airborne again - that's a bounce!
                bounces.append(
                    {
                        "ground_start": ground_start,
                        "ground_end": time_sec,
                        "duration": time_sec - ground_start,
                    }
                )
                ground_start = None

        elif alt_m < 0.1 and was_airborne and ground_start is None:
            # Just touched ground after being airborne
            ground_start = time_sec

    print(f"\n\nBOUNCE EVENTS FOUND: {len(bounces)}")
    print("-" * 80)

    if bounces:
        print(f"{'Start':>8s} {'End':>8s} {'Duration':>10s} {'Event':30s}")
        print("-" * 80)
        for bounce in bounces[:20]:  # Show first 20
            print(
                f"{bounce['ground_start']:8.1f} {bounce['ground_end']:8.1f} "
                f"{bounce['duration']:10.2f} Aircraft touched ground, then lifted off"
            )
    else:
        print("No bounce events detected")

    # Analyze altitude profile over time (every 10 seconds)
    print("\n\nALTITUDE PROFILE (every 10 seconds):")
    print("-" * 80)
    print(f"{'Time':>6s} {'Alt_m':>8s} {'Alt_ft':>8s} {'Climb':>8s} {'Speed':>8s} {'OnGnd':>7s}")
    print("-" * 80)

    cursor.execute("""
        SELECT
            timestamp_ms/1000.0 as time_sec,
            position_y as altitude_m,
            velocity_y as climb_mps,
            airspeed_kts,
            on_ground
        FROM telemetry
        WHERE CAST(timestamp_ms/1000 AS INTEGER) % 10 = 0
        ORDER BY timestamp_ms
        LIMIT 30
    """)

    for row in cursor.fetchall():
        time_sec, alt_m, climb_mps, speed_kts, on_ground = row
        alt_ft = alt_m * 3.28084
        on_gnd_str = "Yes" if on_ground else "No"
        print(
            f"{time_sec:6.0f} {alt_m:8.1f} {alt_ft:8.0f} {climb_mps:8.2f} "
            f"{speed_kts:8.1f} {on_gnd_str:>7s}"
        )

    # Check for inconsistency: high speed + on_ground + altitude=0
    cursor.execute("""
        SELECT COUNT(*) FROM telemetry
        WHERE airspeed_kts > 40 AND on_ground = 1 AND position_y < 0.1
    """)
    stuck_frames = cursor.fetchone()[0]

    if stuck_frames > 0:
        print(f"\n\n⚠️  WARNING: Found {stuck_frames} frames where:")
        print("   - Airspeed > 40 knots")
        print("   - on_ground = True")
        print("   - altitude = 0")
        print("   This suggests the aircraft might be 'stuck' at ground level")

        # Show examples
        print("\nExamples:")
        print("-" * 80)
        print(f"{'Time':>6s} {'Alt_m':>8s} {'Speed':>8s} {'Climb':>8s} {'OnGnd':>7s}")
        print("-" * 80)

        cursor.execute("""
            SELECT
                timestamp_ms/1000.0 as time_sec,
                position_y,
                airspeed_kts,
                velocity_y,
                on_ground
            FROM telemetry
            WHERE airspeed_kts > 40 AND on_ground = 1 AND position_y < 0.1
            ORDER BY timestamp_ms
            LIMIT 10
        """)

        for row in cursor.fetchall():
            time_sec, alt_m, speed_kts, climb_mps, on_ground = row
            on_gnd_str = "Yes" if on_ground else "No"
            print(
                f"{time_sec:6.0f} {alt_m:8.1f} {speed_kts:8.1f} {climb_mps:8.2f} {on_gnd_str:>7s}"
            )

    conn.close()


if __name__ == "__main__":
    db_path = "/tmp/airborne_telemetry_20251028_171921.db"
    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    analyze_altitude_bounce(db_path)

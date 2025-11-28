#!/usr/bin/env python3
"""Analyze force vector telemetry to identify runaway acceleration bug."""

import sqlite3
import sys


def analyze_forces(db_path: str):
    """Analyze force vectors from telemetry database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 80)
    print("FORCE VECTOR ANALYSIS - Runaway Acceleration Investigation")
    print("=" * 80)

    # Get time range
    cursor.execute("SELECT MIN(timestamp_ms)/1000.0, MAX(timestamp_ms)/1000.0 FROM forces")
    time_range = cursor.fetchone()
    start_time = time_range[0]
    end_time = time_range[1]

    print(f"\nForce data available from {start_time:.1f}s to {end_time:.1f}s")

    # Get data from the middle of the high-speed period
    analysis_start = start_time + 5
    analysis_end = min(start_time + 15, end_time)

    cursor.execute(f"""
        SELECT
            timestamp_ms/1000.0 as time_sec,
            thrust_mag,
            drag_mag,
            lift_mag,
            weight_mag,
            external_mag,
            total_mag,
            thrust_x, thrust_z,
            drag_x, drag_z,
            total_x, total_z,
            accel_from_forces_x,
            accel_from_forces_z,
            accel_from_forces_mag,
            actual_accel_x,
            actual_accel_z,
            actual_accel_mag
        FROM forces
        WHERE timestamp_ms/1000.0 BETWEEN {analysis_start} AND {analysis_end}
        ORDER BY timestamp_ms
    """)

    rows = cursor.fetchall()

    if not rows:
        print("ERROR: No force data found in 70-80 second range!")
        return

    print(
        f"\nAnalyzing {len(rows)} force records between {analysis_start:.1f}-{analysis_end:.1f} seconds\n"
    )

    # Analyze first 10 samples
    print("FORCE MAGNITUDES (First 10 samples):")
    print("-" * 80)
    print(
        f"{'Time':>6s} {'Thrust':>8s} {'Drag':>8s} {'Total':>8s} {'CalcAccel':>10s} {'ActualAccel':>12s} {'Diff':>8s}"
    )
    print("-" * 80)

    for i, row in enumerate(rows[:10]):
        time_sec = row[0]
        thrust = row[1]
        drag = row[2]
        total = row[6]
        calc_accel = row[14]
        actual_accel = row[17]
        diff = actual_accel - calc_accel

        print(
            f"{time_sec:6.1f} {thrust:8.0f}N {drag:8.0f}N {total:8.0f}N {calc_accel:10.2f} {actual_accel:12.2f} {diff:+8.2f}"
        )

    # Check force directions
    print("\n\nFORCE DIRECTIONS (First 5 samples):")
    print("-" * 80)
    print(
        f"{'Time':>6s} {'Thrust_X':>10s} {'Thrust_Z':>10s} {'Drag_X':>10s} {'Drag_Z':>10s} {'Total_X':>10s} {'Total_Z':>10s}"
    )
    print("-" * 80)

    for i, row in enumerate(rows[:5]):
        time_sec = row[0]
        thrust_x = row[7]
        thrust_z = row[8]
        drag_x = row[9]
        drag_z = row[10]
        total_x = row[11]
        total_z = row[12]

        print(
            f"{time_sec:6.1f} {thrust_x:10.1f}N {thrust_z:10.1f}N {drag_x:10.1f}N {drag_z:10.1f}N {total_x:10.1f}N {total_z:10.1f}N"
        )

    # Compare calculated vs actual acceleration vectors
    print("\n\nACCELERATION COMPARISON (First 5 samples):")
    print("-" * 80)
    print(
        f"{'Time':>6s} {'Calc_X':>10s} {'Actual_X':>10s} {'Calc_Z':>10s} {'Actual_Z':>10s} {'Diff_X':>10s} {'Diff_Z':>10s}"
    )
    print("-" * 80)

    for i, row in enumerate(rows[:5]):
        time_sec = row[0]
        calc_x = row[13]  # accel_from_forces_x
        calc_z = row[14]  # accel_from_forces_z
        actual_x = row[16]  # actual_accel_x
        actual_z = row[17]  # actual_accel_z
        diff_x = actual_x - calc_x
        diff_z = actual_z - calc_z

        print(
            f"{time_sec:6.1f} {calc_x:10.2f} {actual_x:10.2f} {calc_z:10.2f} {actual_z:10.2f} {diff_x:+10.2f} {diff_z:+10.2f}"
        )

    # Summary statistics
    print(f"\n\nSUMMARY STATISTICS ({analysis_start:.1f}-{analysis_end:.1f} seconds):")
    print("-" * 80)

    cursor.execute(f"""
        SELECT
            AVG(thrust_mag) as avg_thrust,
            AVG(drag_mag) as avg_drag,
            AVG(total_mag) as avg_total,
            AVG(accel_from_forces_mag) as avg_calc_accel,
            AVG(actual_accel_mag) as avg_actual_accel,
            AVG(actual_accel_mag - accel_from_forces_mag) as avg_diff
        FROM forces
        WHERE timestamp_ms/1000.0 BETWEEN {analysis_start} AND {analysis_end}
    """)

    summary = cursor.fetchone()

    print(f"Average Thrust:           {summary[0]:8.0f}N")
    print(f"Average Drag:             {summary[1]:8.0f}N")
    print(f"Average Total Force:      {summary[2]:8.0f}N")
    print(f"Average Calculated Accel: {summary[3]:8.2f} m/s²")
    print(f"Average Actual Accel:     {summary[4]:8.2f} m/s²")
    print(f"Average Difference:       {summary[5]:+8.2f} m/s²")

    # Check if external forces are present
    cursor.execute(f"""
        SELECT
            COUNT(*) as count,
            AVG(external_mag) as avg_external,
            MAX(external_mag) as max_external
        FROM forces
        WHERE timestamp_ms/1000.0 BETWEEN {analysis_start} AND {analysis_end} AND external_mag > 0.1
    """)

    ext = cursor.fetchone()

    print("\n\nEXTERNAL FORCES:")
    print(f"Records with external force > 0.1N: {ext[0]}")
    if ext[1] is not None:
        print(f"Average external force magnitude:   {ext[1]:8.2f}N")
        print(f"Maximum external force magnitude:   {ext[2]:8.2f}N")
    else:
        print("Average external force magnitude:   0.00N")
        print("Maximum external force magnitude:   0.00N")

    # Determine the bug
    print("\n\n" + "=" * 80)
    print("DIAGNOSIS:")
    print("=" * 80)

    if abs(summary[5]) < 0.01:
        print("✅ Calculated acceleration MATCHES actual acceleration")
        print("   → Force calculations are correct")
        print("   → Integration is correct")
        print("   → Bug must be elsewhere (telemetry timing, coordinate systems, etc.)")
    else:
        print("❌ Calculated acceleration DOES NOT MATCH actual acceleration")
        print(f"   → Difference: {summary[5]:+.2f} m/s²")
        print("   → This indicates a bug in either:")
        print("     1. Force application (forces not being applied correctly)")
        print("     2. Velocity integration (sign error or missing forces)")
        print("     3. State acceleration calculation (not reflecting actual velocity change)")

    if summary[2] < 0:
        print("\n⚠️  Average total force is NEGATIVE (backward)")
        print("   → Aircraft should be DECELERATING")
        if summary[4] > 0:
            print("   → But actual acceleration is POSITIVE (forward)")
            print("   → CRITICAL BUG: Forces and acceleration have opposite signs!")

    conn.close()


if __name__ == "__main__":
    db_path = "/tmp/airborne_telemetry_20251028_162458.db"
    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    analyze_forces(db_path)

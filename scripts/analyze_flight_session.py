#!/usr/bin/env python3
"""Analyze flight session telemetry and provide pilot feedback."""

import sqlite3
import sys
from pathlib import Path


def analyze_flight(db_path: str):
    """Analyze flight telemetry and provide detailed feedback."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 80)
    print("FLIGHT SESSION ANALYSIS")
    print("=" * 80)

    # Get session overview
    cursor.execute("""
        SELECT
            COUNT(*) as total_frames,
            MIN(timestamp_ms) as start_time,
            MAX(timestamp_ms) as end_time,
            MAX(altitude_m) as max_altitude,
            MAX(airspeed_mps) as max_airspeed
        FROM telemetry
    """)
    overview = cursor.fetchone()
    duration_sec = (overview[2] - overview[1]) / 1000.0  # Convert ms to seconds

    print("\n📊 SESSION OVERVIEW")
    print(f"Duration: {duration_sec:.1f} seconds ({duration_sec / 60:.1f} minutes)")
    print(f"Total frames: {overview[0]}")
    if overview[3] is not None:
        print(f"Max altitude: {overview[3]:.1f}m ({overview[3] * 3.28084:.0f}ft)")
    else:
        print("Max altitude: 0.0m (stayed on ground)")
    if overview[4] is not None:
        print(f"Max airspeed: {overview[4]:.1f}m/s ({overview[4] * 1.94384:.0f}kts)")
    else:
        print("Max airspeed: 0.0m/s (no airspeed recorded)")

    # Flight phases
    cursor.execute("""
        SELECT
            SUM(CASE WHEN on_ground = 1 THEN 1 ELSE 0 END) as ground_frames,
            SUM(CASE WHEN on_ground = 0 THEN 1 ELSE 0 END) as airborne_frames
        FROM telemetry
    """)
    phases = cursor.fetchone()
    print("\n✈️ FLIGHT PHASES")
    print(f"Time on ground: {phases[0] / 60:.1f}s")
    print(f"Time airborne: {phases[1] / 60:.1f}s")

    # Control input analysis
    cursor.execute("""
        SELECT
            AVG(ABS(elevator)) as avg_pitch_input,
            AVG(ABS(aileron)) as avg_roll_input,
            AVG(ABS(rudder)) as avg_yaw_input,
            MAX(ABS(elevator)) as max_pitch_input,
            MAX(ABS(aileron)) as max_roll_input,
            MAX(ABS(rudder)) as max_yaw_input,
            AVG(throttle) as avg_throttle,
            MAX(throttle) as max_throttle
        FROM telemetry
        WHERE on_ground = 0
    """)
    inputs = cursor.fetchone()

    print("\n🎮 CONTROL INPUTS (AIRBORNE)")
    if inputs[0] is not None:
        print("Pitch control:")
        print(f"  Average: {inputs[0] * 100:.1f}%")
        print(f"  Maximum: {inputs[3] * 100:.1f}%")
        print("Roll control:")
        print(f"  Average: {inputs[1] * 100:.1f}%")
        print(f"  Maximum: {inputs[4] * 100:.1f}%")
        print("Yaw control:")
        print(f"  Average: {inputs[2] * 100:.1f}%")
        print(f"  Maximum: {inputs[5] * 100:.1f}%")
        print("Throttle:")
        print(f"  Average: {inputs[6] * 100:.1f}%")
        print(f"  Maximum: {inputs[7] * 100:.1f}%")
    else:
        print("No airborne time recorded")

    # Note: Trim is not yet logged in telemetry, skip for now
    # Will add trim columns in future update
    trim = (None, None, None, 0)

    print("\n⚖️ TRIM USAGE (AIRBORNE)")
    if trim[0] is not None:
        print(f"Pitch trim average: {trim[0] * 100:.1f}%")
        print(f"Pitch trim range: {trim[1] * 100:.1f}% to {trim[2] * 100:.1f}%")
        print(f"Trim adjustments: ~{trim[3]} changes")
    else:
        print("No airborne time recorded")

    # Pitch stability analysis (manual stdev calculation)
    cursor.execute("""
        SELECT
            AVG(ABS(pitch_deg)) as avg_pitch_angle,
            AVG(pitch_deg * pitch_deg) - AVG(pitch_deg) * AVG(pitch_deg) as variance,
            MIN(pitch_deg) as min_pitch,
            MAX(pitch_deg) as max_pitch
        FROM telemetry
        WHERE on_ground = 0 AND airspeed_mps > 20
    """)
    pitch_stats = cursor.fetchone()

    print("\n📐 PITCH CONTROL ANALYSIS (CRUISE)")
    if pitch_stats[0] is not None and pitch_stats[1] is not None:
        import math

        pitch_stdev = math.sqrt(max(0, pitch_stats[1]))  # sqrt of variance
        print(f"Average pitch angle: {pitch_stats[0]:.1f}°")
        print(f"Pitch variation (stdev): {pitch_stdev:.1f}°")
        print(f"Pitch range: {pitch_stats[2]:.1f}° to {pitch_stats[3]:.1f}°")

        if pitch_stdev > 10:
            print("⚠️  HIGH pitch variation - aircraft is oscillating")
        elif pitch_stdev > 5:
            print("⚠️  MODERATE pitch variation - could be smoother")
        else:
            print("✅ GOOD pitch stability")
    else:
        print("No cruise data available")

    # Altitude stability analysis
    cursor.execute("""
        SELECT
            AVG(altitude_m) as avg_altitude,
            AVG(altitude_m * altitude_m) - AVG(altitude_m) * AVG(altitude_m) as variance,
            MIN(altitude_m) as min_alt,
            MAX(altitude_m) as max_alt
        FROM telemetry
        WHERE on_ground = 0 AND airspeed_mps > 20
    """)
    alt_stats = cursor.fetchone()

    print("\n🗻 ALTITUDE CONTROL ANALYSIS (CRUISE)")
    if alt_stats[0] is not None and alt_stats[1] is not None:
        import math

        alt_stdev = math.sqrt(max(0, alt_stats[1]))
        print(f"Average altitude: {alt_stats[0]:.0f}m ({alt_stats[0] * 3.28084:.0f}ft)")
        print(f"Altitude variation (stdev): {alt_stdev:.1f}m ({alt_stdev * 3.28084:.0f}ft)")
        print(f"Altitude range: {alt_stats[2]:.0f}m to {alt_stats[3]:.0f}m")

        if alt_stdev > 50:
            print("⚠️  HIGH altitude variation - difficulty maintaining level flight")
        elif alt_stdev > 20:
            print("⚠️  MODERATE altitude variation - practice level flight")
        else:
            print("✅ GOOD altitude control")
    else:
        print("No cruise data available")

    # Vertical speed analysis
    cursor.execute("""
        SELECT
            AVG(ABS(vertical_speed_mps)) as avg_vspeed,
            MAX(vertical_speed_mps) as max_climb,
            MIN(vertical_speed_mps) as max_descent
        FROM telemetry
        WHERE on_ground = 0
    """)
    vspeed_stats = cursor.fetchone()

    print("\n⬆️ VERTICAL SPEED ANALYSIS")
    if vspeed_stats[0] is not None:
        print(
            f"Average vertical speed: {vspeed_stats[0]:.1f}m/s ({vspeed_stats[0] * 196.85:.0f}fpm)"
        )
        print(f"Max climb rate: {vspeed_stats[1]:.1f}m/s ({vspeed_stats[1] * 196.85:.0f}fpm)")
        print(f"Max descent rate: {vspeed_stats[2]:.1f}m/s ({vspeed_stats[2] * 196.85:.0f}fpm)")

    # Recommendations
    print("\n💡 RECOMMENDATIONS")

    if inputs[0] is not None and inputs[0] > 0.3:
        print("❗ You're making large pitch inputs. Try:")
        print("   - Make smaller, more precise corrections")
        print("   - Use trim to relieve control pressure")
        print("   - Let trim do the work of maintaining altitude")

    if trim[3] is not None and trim[3] < 5:
        print("❗ Very few trim adjustments detected. Remember:")
        print("   - Use Shift+Semicolon/Ctrl+Semicolon for trim")
        print("   - Trim out control forces instead of holding inputs")
        print("   - Proper technique: adjust yoke, then trim to neutral")

    if pitch_stats[0] is not None and pitch_stats[1] is not None:
        import math

        pitch_stdev = math.sqrt(max(0, pitch_stats[1]))
        if pitch_stdev > 5:
            print("❗ Pitch oscillations detected. Try:")
            print("   - Smaller control inputs (5% increments)")
            print("   - Use Right Shift to center controls")
            print("   - Trim more aggressively")

    if alt_stats[0] is not None and alt_stats[1] is not None:
        import math

        alt_stdev = math.sqrt(max(0, alt_stats[1]))
        if alt_stdev > 30:
            print("❗ Altitude control needs work. Focus on:")
            print("   - Watch vertical speed, not just altitude")
            print("   - Make pitch adjustments early (1-2° changes)")
            print("   - Trim for level flight, adjust power for altitude")

    print("\n" + "=" * 80)

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        # Find most recent telemetry file
        import glob

        files = glob.glob("/tmp/airborne_telemetry_*.db")
        if not files:
            print("No telemetry files found in /tmp/")
            sys.exit(1)
        db_path = max(files, key=lambda x: Path(x).stat().st_mtime)
        print(f"Using telemetry file: {db_path}\n")

    analyze_flight(db_path)

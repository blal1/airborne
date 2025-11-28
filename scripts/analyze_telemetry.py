#!/usr/bin/env python3
"""Analyze telemetry data from a flight recording.

Usage:
    python scripts/analyze_telemetry.py /tmp/airborne_telemetry_YYYYMMDD_HHMMSS.db
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from airborne.telemetry import TelemetryAnalyzer


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/analyze_telemetry.py <telemetry_db_path>")
        print("\nExample:")
        print("  python scripts/analyze_telemetry.py /tmp/airborne_telemetry_20251027_123456.db")
        sys.exit(1)

    db_path = sys.argv[1]

    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}")
        sys.exit(1)

    print(f"Analyzing telemetry from: {db_path}")
    print("=" * 80)

    analyzer = TelemetryAnalyzer(db_path)

    # Get takeoff performance
    print("\n📊 TAKEOFF PERFORMANCE")
    print("-" * 80)
    takeoff = analyzer.get_takeoff_performance()

    if "error" in takeoff:
        print(f"⚠️  {takeoff['error']}")
    elif not takeoff.get("rotation_achieved"):
        print("❌ Did NOT reach rotation speed (55 knots)")
        print(f"   Max airspeed reached: {takeoff['max_airspeed_kts']:.1f} knots")
        print(f"   Time to max speed: {takeoff['time_to_max_seconds']:.1f} seconds")
        print(f"\n   📝 Note: {takeoff['note']}")
    else:
        print(f"✅ Reached rotation speed in {takeoff['time_to_rotation_seconds']:.1f} seconds")
        print(f"   Rotation speed: {takeoff['rotation_speed_kts']:.1f} knots")
        print(f"   Thrust at rotation: {takeoff['thrust_at_rotation_n']:.1f} N")
        print(f"   Average thrust: {takeoff['avg_thrust_n']:.1f} N")
        if takeoff["avg_drag_n"] is not None:
            print(f"   Average drag: {takeoff['avg_drag_n']:.1f} N")
        else:
            print("   Average drag: N/A (not logged)")
        if takeoff["avg_acceleration_mps2"] is not None:
            print(f"   Average acceleration: {takeoff['avg_acceleration_mps2']:.3f} m/s²")
        else:
            print("   Average acceleration: N/A (not logged)")

        # Compare to expected performance
        expected_time = 15.0  # C172 should reach 55 knots in ~15 seconds
        performance_pct = (expected_time / takeoff["time_to_rotation_seconds"]) * 100
        print(f"\n   Performance: {performance_pct:.1f}% of realistic C172")
        if performance_pct < 70:
            print(f"   ❌ Still too slow (expected ~{expected_time:.0f} seconds)")
        elif performance_pct < 90:
            print(f"   ⚠️  Getting better (target: ~{expected_time:.0f} seconds)")
        else:
            print(f"   ✅ Good performance! (close to {expected_time:.0f} seconds target)")

    # Get thrust curve
    print("\n📈 THRUST VS AIRSPEED CURVE")
    print("-" * 80)
    thrust_curve = analyzer.get_thrust_curve(speed_increment_kts=5.0)

    if not thrust_curve:
        print("No thrust data available (engine may not have been running)")
    else:
        print("Speed (kts)  │ Thrust (N) │ Drag (N) │ Net (N) │ J      │ Correction │ Samples")
        print("─" * 85)
        for row in thrust_curve:
            speed = row["avg_airspeed_kts"]
            thrust = row["avg_thrust_n"]
            drag = row["avg_drag_n"] or 0
            net = thrust - drag
            j = row["avg_advance_ratio"] or 0
            corr = row["avg_thrust_correction"] or 0
            samples = row["sample_count"]

            print(
                f"{speed:>11.1f}  │ {thrust:>10.1f} │ {drag:>8.1f} │ {net:>7.1f} │ {j:>6.3f} │ {corr:>10.3f} │ {samples:>7d}"
            )

    # Overall summary
    print("\n📋 FLIGHT SUMMARY")
    print("-" * 80)
    summary = analyzer.get_summary()
    print(f"Total frames: {summary['frame_count']}")
    if summary.get("duration_seconds"):
        print(
            f"Flight duration: {summary['duration_seconds']:.1f} seconds ({summary['duration_seconds'] / 60:.1f} minutes)"
        )
    if summary.get("max_airspeed_kts") is not None:
        print(f"Max airspeed: {summary['max_airspeed_kts']:.1f} knots")
    if summary.get("max_altitude_m") is not None:
        print(f"Max altitude: {summary['max_altitude_m']:.1f} meters")
    if summary.get("max_thrust_n") is not None:
        print(f"Max thrust: {summary['max_thrust_n']:.1f} N")
        if summary.get("avg_thrust_n") is not None:
            print(f"Avg thrust: {summary['avg_thrust_n']:.1f} N")
    if summary.get("max_acceleration_mps2") is not None:
        print(f"Max acceleration: {summary['max_acceleration_mps2']:.3f} m/s²")
        if summary.get("avg_acceleration_mps2") is not None:
            print(f"Avg acceleration: {summary['avg_acceleration_mps2']:.3f} m/s²")

    analyzer.close()

    print("\n" + "=" * 80)
    print("✅ Analysis complete!")
    print("\nTo export data to CSV:")
    print(
        f"  python -c \"from airborne.telemetry import TelemetryAnalyzer; a = TelemetryAnalyzer('{db_path}'); a.export_to_csv('telemetry.csv')\""
    )


if __name__ == "__main__":
    main()

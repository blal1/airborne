#!/usr/bin/env python3
"""Test script for CallsignBuilder - verifies phonetic alphabet assembly."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from airborne.plugins.radio.callsign_builder import CallsignBuilder


def test_callsign_builder():
    """Test callsign builder with various inputs."""
    builder = CallsignBuilder(voice="pilot")

    print("=" * 80)
    print("CALLSIGN BUILDER TEST")
    print("=" * 80)

    # Test 1: Basic callsign
    print("\n1. Callsign: N123AB")
    files = builder.build_callsign("N123AB")
    print(f"   Files: {' → '.join(files)}")
    print("   Audio: November One Two Three Alpha Bravo")

    # Test 2: Canadian callsign
    print("\n2. Callsign: C-GABC")
    files = builder.build_callsign("C-GABC")
    print(f"   Files: {' → '.join(files)}")
    print("   Audio: Charlie Golf Alpha Bravo Charlie")

    # Test 3: Callsign with 9
    print("\n3. Callsign: N912CD")
    files = builder.build_callsign("N912CD")
    print(f"   Files: {' → '.join(files)}")
    print("   Audio: November Niner One Two Charlie Delta")

    # Test 4: Frequency
    print("\n4. Frequency: 121.5 MHz")
    files = builder.build_frequency(121.5)
    print(f"   Files: {' → '.join(files)}")
    print("   Audio: One Two One Decimal Five")

    # Test 5: Frequency with .3
    print("\n5. Frequency: 118.3 MHz")
    files = builder.build_frequency(118.3)
    print(f"   Files: {' → '.join(files)}")
    print("   Audio: One One Eight Decimal Three")

    # Test 6: Altitude
    print("\n6. Altitude: 2500 feet")
    files = builder.build_altitude(2500)
    print(f"   Files: {' → '.join(files)}")
    print("   Audio: Two Thousand Five Hundred")

    # Test 7: Altitude 1000
    print("\n7. Altitude: 1000 feet")
    files = builder.build_altitude(1000)
    print(f"   Files: {' → '.join(files)}")
    print("   Audio: One Thousand")

    # Test 8: Heading
    print("\n8. Heading: 90 degrees")
    files = builder.build_heading(90)
    print(f"   Files: {' → '.join(files)}")
    print("   Audio: Zero Niner Zero")

    # Test 9: Runway
    print("\n9. Runway: 31")
    files = builder.build_runway("31")
    print(f"   Files: {' → '.join(files)}")
    print("   Audio: Three One")

    # Test 10: Runway with suffix
    print("\n10. Runway: 09L")
    files = builder.build_runway("09L")
    print(f"   Files: {' → '.join(files)}")
    print("   Audio: Zero Niner Lima")

    # Test 11: Verify files exist
    print("\n" + "=" * 80)
    print("FILE VERIFICATION")
    print("=" * 80)

    test_files = builder.build_callsign("N123AB")
    paths = builder.get_file_paths(test_files)

    missing = []
    for path in paths:
        if path.exists():
            print(f"✓ {path.name}")
        else:
            print(f"✗ {path.name} (MISSING)")
            missing.append(path)

    if missing:
        print(f"\n⚠️  {len(missing)} files are missing!")
        print("Run: python3 scripts/generate_speech.py pilot")
        return False
    else:
        print(f"\n✓ All {len(paths)} files exist!")
        return True


if __name__ == "__main__":
    success = test_callsign_builder()
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""Test script to investigate pyttsx3 issues with multiple TTS generations.

This script tests various approaches to using pyttsx3 for on-the-fly TTS generation.
"""

import tempfile
import time
from pathlib import Path


def test_basic_sequential():
    """Test basic sequential TTS generation with a single engine instance."""
    import pyttsx3

    print("\n" + "=" * 60)
    print("TEST 1: Basic sequential with single engine instance")
    print("=" * 60)

    engine = pyttsx3.init()
    engine.setProperty("rate", 180)

    messages = [
        "Hello, this is message one.",
        "This is the second message.",
        "And here is the third message.",
        "Finally, the fourth message.",
    ]

    temp_dir = Path(tempfile.mkdtemp())
    print(f"Output directory: {temp_dir}")

    for i, msg in enumerate(messages):
        output_path = temp_dir / f"test1_msg_{i}.wav"
        print(f"  [{i + 1}/{len(messages)}] Generating: '{msg}'")

        try:
            engine.save_to_file(msg, str(output_path))
            engine.runAndWait()

            if output_path.exists():
                size = output_path.stat().st_size
                print(f"    -> OK: {output_path.name} ({size} bytes)")
            else:
                print("    -> FAILED: File not created")
        except Exception as e:
            print(f"    -> ERROR: {e}")

        time.sleep(0.5)

    engine.stop()
    print("\nTest 1 complete.")
    return temp_dir


def test_new_engine_each_time():
    """Test creating a new engine instance for each message."""
    import pyttsx3

    print("\n" + "=" * 60)
    print("TEST 2: New engine instance for each message")
    print("=" * 60)

    messages = [
        "Hello, this is message one.",
        "This is the second message.",
        "And here is the third message.",
        "Finally, the fourth message.",
    ]

    temp_dir = Path(tempfile.mkdtemp())
    print(f"Output directory: {temp_dir}")

    for i, msg in enumerate(messages):
        output_path = temp_dir / f"test2_msg_{i}.wav"
        print(f"  [{i + 1}/{len(messages)}] Generating: '{msg}'")

        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 180)
            engine.save_to_file(msg, str(output_path))
            engine.runAndWait()
            engine.stop()
            del engine

            if output_path.exists():
                size = output_path.stat().st_size
                print(f"    -> OK: {output_path.name} ({size} bytes)")
            else:
                print("    -> FAILED: File not created")
        except Exception as e:
            print(f"    -> ERROR: {e}")

        time.sleep(0.5)

    print("\nTest 2 complete.")
    return temp_dir


def test_with_explicit_driver():
    """Test with explicit driver selection (nsss for macOS, sapi5 for Windows)."""
    import platform

    import pyttsx3

    print("\n" + "=" * 60)
    print("TEST 3: Explicit driver selection")
    print("=" * 60)

    system = platform.system()
    if system == "Darwin":
        driver = "nsss"
    elif system == "Windows":
        driver = "sapi5"
    else:
        driver = "espeak"

    print(f"Platform: {system}, Driver: {driver}")

    messages = [
        "Hello, this is message one.",
        "This is the second message.",
        "And here is the third message.",
    ]

    temp_dir = Path(tempfile.mkdtemp())
    print(f"Output directory: {temp_dir}")

    for i, msg in enumerate(messages):
        output_path = temp_dir / f"test3_msg_{i}.wav"
        print(f"  [{i + 1}/{len(messages)}] Generating: '{msg}'")

        try:
            engine = pyttsx3.init(driverName=driver)
            engine.setProperty("rate", 180)
            engine.save_to_file(msg, str(output_path))
            engine.runAndWait()
            engine.stop()
            del engine

            if output_path.exists():
                size = output_path.stat().st_size
                print(f"    -> OK: {output_path.name} ({size} bytes)")
            else:
                print("    -> FAILED: File not created")
        except Exception as e:
            print(f"    -> ERROR: {e}")

        time.sleep(0.5)

    print("\nTest 3 complete.")
    return temp_dir


def test_queue_multiple_then_run():
    """Test queuing multiple messages before calling runAndWait."""
    import pyttsx3

    print("\n" + "=" * 60)
    print("TEST 4: Queue multiple messages, then runAndWait once")
    print("=" * 60)

    engine = pyttsx3.init()
    engine.setProperty("rate", 180)

    messages = [
        "Hello, this is message one.",
        "This is the second message.",
        "And here is the third message.",
    ]

    temp_dir = Path(tempfile.mkdtemp())
    print(f"Output directory: {temp_dir}")

    # Queue all files first
    for i, msg in enumerate(messages):
        output_path = temp_dir / f"test4_msg_{i}.wav"
        print(f"  Queuing [{i + 1}/{len(messages)}]: '{msg}' -> {output_path.name}")
        engine.save_to_file(msg, str(output_path))

    # Run once
    print("  Running engine.runAndWait()...")
    try:
        engine.runAndWait()
        print("  runAndWait completed.")
    except Exception as e:
        print(f"  ERROR in runAndWait: {e}")

    # Check results
    for i in range(len(messages)):
        output_path = temp_dir / f"test4_msg_{i}.wav"
        if output_path.exists():
            size = output_path.stat().st_size
            print(f"    -> {output_path.name}: OK ({size} bytes)")
        else:
            print(f"    -> {output_path.name}: FAILED (not created)")

    engine.stop()
    print("\nTest 4 complete.")
    return temp_dir


def test_with_callbacks():
    """Test with callbacks to understand engine state."""
    import pyttsx3

    print("\n" + "=" * 60)
    print("TEST 5: With callbacks to monitor engine state")
    print("=" * 60)

    def on_start(name):
        print(f"    [callback] Started: {name}")

    def on_word(name, location, length):
        pass  # Too verbose

    def on_end(name, completed):
        print(f"    [callback] Ended: {name}, completed={completed}")

    def on_error(name, exception):
        print(f"    [callback] Error in {name}: {exception}")

    engine = pyttsx3.init()
    engine.setProperty("rate", 180)

    # Connect callbacks
    engine.connect("started-utterance", on_start)
    engine.connect("finished-utterance", on_end)
    engine.connect("error", on_error)

    messages = [
        "Hello, this is message one.",
        "This is the second message.",
        "And here is the third message.",
    ]

    temp_dir = Path(tempfile.mkdtemp())
    print(f"Output directory: {temp_dir}")

    for i, msg in enumerate(messages):
        output_path = temp_dir / f"test5_msg_{i}.wav"
        print(f"  [{i + 1}/{len(messages)}] Generating: '{msg}'")

        try:
            engine.save_to_file(msg, str(output_path))
            engine.runAndWait()

            if output_path.exists():
                size = output_path.stat().st_size
                print(f"    -> OK: {output_path.name} ({size} bytes)")
            else:
                print("    -> FAILED: File not created")
        except Exception as e:
            print(f"    -> ERROR: {e}")

        time.sleep(0.5)

    engine.stop()
    print("\nTest 5 complete.")
    return temp_dir


def test_speak_vs_save():
    """Test if speak() works after save_to_file() fails."""
    import pyttsx3

    print("\n" + "=" * 60)
    print("TEST 6: Compare speak() vs save_to_file() behavior")
    print("=" * 60)

    engine = pyttsx3.init()
    engine.setProperty("rate", 180)

    temp_dir = Path(tempfile.mkdtemp())
    print(f"Output directory: {temp_dir}")

    # First: save to file
    print("\n  Part A: save_to_file() x3")
    for i in range(3):
        output_path = temp_dir / f"test6a_msg_{i}.wav"
        msg = f"Save to file message {i + 1}"
        print(f"    [{i + 1}] '{msg}'")
        try:
            engine.save_to_file(msg, str(output_path))
            engine.runAndWait()
            if output_path.exists():
                print(f"        -> OK ({output_path.stat().st_size} bytes)")
            else:
                print("        -> FAILED")
        except Exception as e:
            print(f"        -> ERROR: {e}")

    # Then: try speak() (to audio output)
    print("\n  Part B: speak() x3 (will play audio)")
    for i in range(3):
        msg = f"Speak message {i + 1}"
        print(f"    [{i + 1}] '{msg}'")
        try:
            engine.say(msg)
            engine.runAndWait()
            print("        -> OK (played)")
        except Exception as e:
            print(f"        -> ERROR: {e}")

    engine.stop()
    print("\nTest 6 complete.")
    return temp_dir


def test_engine_busy_check():
    """Test if engine reports busy state."""
    import pyttsx3

    print("\n" + "=" * 60)
    print("TEST 7: Check engine busy state")
    print("=" * 60)

    engine = pyttsx3.init()
    engine.setProperty("rate", 180)

    temp_dir = Path(tempfile.mkdtemp())

    messages = ["Message one.", "Message two.", "Message three."]

    for i, msg in enumerate(messages):
        output_path = temp_dir / f"test7_msg_{i}.wav"
        print(f"  [{i + 1}] Generating: '{msg}'")

        # Check busy state before
        try:
            busy = engine.isBusy()
            print(f"      Before: isBusy={busy}")
        except AttributeError:
            print("      Before: isBusy not available")

        try:
            engine.save_to_file(msg, str(output_path))

            # Check busy state after save_to_file
            try:
                busy = engine.isBusy()
                print(f"      After save_to_file: isBusy={busy}")
            except AttributeError:
                pass

            engine.runAndWait()

            # Check busy state after runAndWait
            try:
                busy = engine.isBusy()
                print(f"      After runAndWait: isBusy={busy}")
            except AttributeError:
                pass

            if output_path.exists():
                print(f"      -> OK ({output_path.stat().st_size} bytes)")
            else:
                print("      -> FAILED")
        except Exception as e:
            print(f"      -> ERROR: {e}")

    engine.stop()
    print("\nTest 7 complete.")
    return temp_dir


def play_with_fmod(wav_path):
    """Try to play a WAV file with FMOD (if available)."""
    try:
        import pyfmodex

        system = pyfmodex.System()
        system.init()

        sound = system.create_sound(str(wav_path))
        channel = sound.play()

        print(f"  Playing {wav_path.name} with FMOD...")
        while channel.is_playing:
            time.sleep(0.1)

        sound.release()
        system.close()
        return True
    except ImportError:
        print("  FMOD (pyfmodex) not available, skipping playback")
        return False
    except Exception as e:
        print(f"  FMOD playback error: {e}")
        return False


def test_realtime_tts_class():
    """Test the RealtimeTTS class from airborne.audio.realtime_tts."""
    print("\n" + "=" * 60)
    print("TEST 8: RealtimeTTS class (production implementation)")
    print("=" * 60)

    try:
        from airborne.audio.realtime_tts import RealtimeTTS
    except ImportError as e:
        print(f"  Could not import RealtimeTTS: {e}")
        return None

    tts = RealtimeTTS(rate=180)
    print(f"  Output directory: {tts.output_dir}")

    messages = [
        "Hello, this is the first message.",
        "This is the second message.",
        "And here comes the third message.",
        "Finally, the fourth and last message.",
    ]

    results = []
    for i, msg in enumerate(messages):
        print(f"  [{i + 1}/{len(messages)}] Generating: '{msg}'")
        result = tts.generate(msg)
        if result and result.exists():
            size = result.stat().st_size
            status = "OK" if size > 4096 else "CORRUPTED (too small)"
            print(f"    -> {status}: {result.name} ({size} bytes)")
            results.append((result, size))
        else:
            print("    -> FAILED: No file generated")
            results.append((None, 0))

    # Test cache
    print("\n  Testing cache (regenerating first message)...")
    result = tts.generate(messages[0])
    if result:
        print(f"    -> Cache hit: {result.name}")
    else:
        print("    -> FAILED")

    # Cleanup
    tts.cleanup()
    print("\nTest 8 complete.")
    return tts.output_dir


def main():
    """Run all tests."""
    print("pyttsx3 Investigation Script")
    print("=" * 60)

    import platform

    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Python: {platform.python_version()}")

    try:
        import pyttsx3

        print(
            f"pyttsx3 version: {pyttsx3.__version__ if hasattr(pyttsx3, '__version__') else 'unknown'}"
        )
    except ImportError:
        print("ERROR: pyttsx3 not installed. Run: pip install pyttsx3")
        return 1

    # Run tests
    test_dirs = []

    try:
        test_dirs.append(test_basic_sequential())
    except Exception as e:
        print(f"Test 1 failed with exception: {e}")

    try:
        test_dirs.append(test_new_engine_each_time())
    except Exception as e:
        print(f"Test 2 failed with exception: {e}")

    try:
        test_dirs.append(test_with_explicit_driver())
    except Exception as e:
        print(f"Test 3 failed with exception: {e}")

    try:
        test_dirs.append(test_queue_multiple_then_run())
    except Exception as e:
        print(f"Test 4 failed with exception: {e}")

    try:
        test_dirs.append(test_with_callbacks())
    except Exception as e:
        print(f"Test 5 failed with exception: {e}")

    # Skip test 6 (speak) as it produces audio output
    # try:
    #     test_dirs.append(test_speak_vs_save())
    # except Exception as e:
    #     print(f"Test 6 failed with exception: {e}")

    try:
        test_dirs.append(test_engine_busy_check())
    except Exception as e:
        print(f"Test 7 failed with exception: {e}")

    try:
        test_dirs.append(test_realtime_tts_class())
    except Exception as e:
        print(f"Test 8 failed with exception: {e}")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("Test output directories:")
    for d in test_dirs:
        if d:
            wav_files = list(d.glob("*.wav"))
            print(f"  {d}: {len(wav_files)} WAV files")

    print("\nDone!")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())

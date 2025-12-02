"""Audio recording module for ATC V2 voice input.

This module provides microphone recording via FMOD's recording API,
with Push-to-Talk support for voice-controlled ATC.
"""

from airborne.audio.recording.audio_recorder import (
    AudioRecorder,
    RecordingDevice,
    RecordingState,
)

__all__ = [
    "AudioRecorder",
    "RecordingDevice",
    "RecordingState",
]

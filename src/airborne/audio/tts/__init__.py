"""TTS (Text-to-Speech) subsystem.

Provides unified TTS with support for:
- Self-voiced: Pre-generated audio chunks (authentic ATC phraseology)
- System: Real-time pyttsx3 synthesis (fluent cross-platform speech)

Usage:
    from airborne.audio.tts import TTSManager, TTSBackend

    tts = TTSManager(audio_engine, backend="system")
    tts.speak("Cleared for takeoff", voice="tower")
"""

from airborne.audio.tts.tts_manager import TTSBackend, TTSManager, VoiceConfig

__all__ = ["TTSManager", "TTSBackend", "VoiceConfig"]

"""TTS (Text-to-Speech) subsystem.

Provides real-time TTS via pyttsx3 for fluent cross-platform speech.

The main TTS functionality is in:
- audio_provider.py: High-level TTS provider interface
- tts_service.py: Background TTS generation service with caching

Usage:
    from airborne.core.i18n import t
    from airborne.audio.tts.audio_provider import AudioSpeechProvider

    tts = AudioSpeechProvider()
    tts.initialize({"language": "en", "audio_engine": engine, "tts_service": service})
    tts.speak(t("system.startup"))
"""

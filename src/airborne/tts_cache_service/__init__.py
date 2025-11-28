"""TTS Cache Service - Subprocess for reliable TTS generation.

This package provides a standalone TTS cache service that runs as a subprocess,
avoiding pyttsx3 threading issues on macOS by running in its own main thread.

Components:
    - service.py: Main service entry point (run as subprocess)
    - protocol.py: JSON IPC protocol definitions
    - cache.py: Disk cache management with settings-based directories
    - client.py: Client for Airborne to communicate with service

Typical usage from Airborne:
    from airborne.tts_cache_service import TTSServiceClient

    async def main():
        client = TTSServiceClient()
        await client.start()  # Spawns subprocess

        # Request TTS
        audio_bytes = await client.generate("altitude 3500")

        # Change settings
        await client.invalidate(rate=200, voice_name="Alex")

        await client.stop()
"""

from airborne.tts_cache_service.cache import TTSDiskCache, VoiceSettings
from airborne.tts_cache_service.client import TTSServiceClient
from airborne.tts_cache_service.protocol import (
    GenerateRequest,
    GenerateResponse,
    InvalidateRequest,
    InvalidateResponse,
    PingRequest,
    PingResponse,
    QueueRequest,
    QueueResponse,
    Request,
    Response,
    StatsRequest,
    StatsResponse,
)

__all__ = [
    # Client
    "TTSServiceClient",
    # Cache
    "TTSDiskCache",
    "VoiceSettings",
    # Protocol
    "Request",
    "Response",
    "GenerateRequest",
    "GenerateResponse",
    "InvalidateRequest",
    "InvalidateResponse",
    "QueueRequest",
    "QueueResponse",
    "PingRequest",
    "PingResponse",
    "StatsRequest",
    "StatsResponse",
]

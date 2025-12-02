"""ATC V2 provider interfaces and implementations.

This package provides pluggable ASR and NLU providers for voice-controlled ATC.
Local implementations use faster-whisper and llama-cpp-python.
Remote implementations can connect to a network-based ATC server.
"""

from airborne.services.atc.providers.base import (
    ATCIntent,
    IASRProvider,
    INLUProvider,
)

__all__ = [
    "ATCIntent",
    "IASRProvider",
    "INLUProvider",
]

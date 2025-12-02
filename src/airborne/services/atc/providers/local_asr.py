"""Local ASR provider using faster-whisper.

This module provides speech-to-text functionality using the faster-whisper
library (CTranslate2-optimized Whisper). It runs entirely offline.

Typical usage:
    asr = LocalASRProvider()
    asr.initialize({"model": "base.en"})

    text = asr.transcribe(audio_bytes)
    print(f"Transcription: {text}")
"""

import io
import logging
import tempfile
import wave
from pathlib import Path
from typing import Any

from airborne.services.atc.providers.base import IASRProvider

logger = logging.getLogger(__name__)

# Try to import faster-whisper
try:
    from faster_whisper import WhisperModel

    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    WhisperModel = None  # type: ignore[assignment,misc]


# Available model sizes
WHISPER_MODELS = [
    "tiny",
    "tiny.en",
    "base",
    "base.en",
    "small",
    "small.en",
    "medium",
    "medium.en",
    "large-v2",
    "large-v3",
]

# Default configuration
DEFAULT_MODEL = "base.en"
DEFAULT_DEVICE = "auto"  # auto, cpu, cuda
DEFAULT_COMPUTE_TYPE = "auto"  # auto, int8, float16, float32


class LocalASRProvider(IASRProvider):
    """Local ASR provider using faster-whisper.

    This provider uses the faster-whisper library for offline speech
    recognition. It downloads models on first use and caches them locally.

    The .en models are English-only and faster/more accurate for English.
    """

    def __init__(self) -> None:
        """Initialize the local ASR provider."""
        self._model: Any = None
        self._model_name: str = DEFAULT_MODEL
        self._device: str = DEFAULT_DEVICE
        self._compute_type: str = DEFAULT_COMPUTE_TYPE
        self._initialized = False

    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the ASR provider with configuration.

        Args:
            config: Configuration dictionary with optional keys:
                - model: Whisper model name (default: "base.en")
                - device: Device to use - "auto", "cpu", "cuda" (default: "auto")
                - compute_type: Compute type - "auto", "int8", "float16" (default: "auto")

        Raises:
            ImportError: If faster-whisper is not installed.
            RuntimeError: If model loading fails.
        """
        if not FASTER_WHISPER_AVAILABLE:
            raise ImportError(
                "faster-whisper is required for local ASR. "
                "Install with: uv add faster-whisper"
            )

        self._model_name = config.get("model", DEFAULT_MODEL)
        self._device = config.get("device", DEFAULT_DEVICE)
        self._compute_type = config.get("compute_type", DEFAULT_COMPUTE_TYPE)

        # Validate model name
        if self._model_name not in WHISPER_MODELS:
            logger.warning(
                f"Unknown model '{self._model_name}', using '{DEFAULT_MODEL}'"
            )
            self._model_name = DEFAULT_MODEL

        logger.info(
            f"Loading Whisper model '{self._model_name}' "
            f"(device={self._device}, compute={self._compute_type})..."
        )

        try:
            self._model = WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
            )
            self._initialized = True
            logger.info(f"Whisper model '{self._model_name}' loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise RuntimeError(f"Failed to load Whisper model: {e}") from e

    def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        """Transcribe audio to text.

        Args:
            audio_data: Raw PCM audio bytes (16-bit signed, mono).
            sample_rate: Audio sample rate in Hz (default: 16000).

        Returns:
            Transcribed text string. Empty string if transcription fails.
        """
        if not self._initialized or not self._model:
            logger.error("ASR provider not initialized")
            return ""

        if not audio_data:
            logger.warning("No audio data provided")
            return ""

        try:
            # Convert PCM to WAV format for faster-whisper
            wav_data = self._pcm_to_wav(audio_data, sample_rate)

            # Write to temporary file (faster-whisper prefers file input)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_data)
                temp_path = f.name

            try:
                # Transcribe
                segments, info = self._model.transcribe(
                    temp_path,
                    language="en",  # Force English for ATC
                    beam_size=5,
                    vad_filter=True,  # Filter out non-speech
                    vad_parameters=dict(
                        min_silence_duration_ms=500,
                        speech_pad_ms=400,
                    ),
                )

                # Combine all segments
                text_parts = []
                for segment in segments:
                    text_parts.append(segment.text.strip())

                transcription = " ".join(text_parts).strip()

                logger.info(
                    f"Transcription ({info.duration:.1f}s audio): '{transcription}'"
                )
                return transcription

            finally:
                # Clean up temp file
                Path(temp_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return ""

    def _pcm_to_wav(self, pcm_data: bytes, sample_rate: int) -> bytes:
        """Convert raw PCM to WAV format.

        Args:
            pcm_data: Raw PCM audio (16-bit signed, mono).
            sample_rate: Sample rate in Hz.

        Returns:
            WAV file bytes.
        """
        buffer = io.BytesIO()

        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)  # Mono
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(sample_rate)
            wav.writeframes(pcm_data)

        return buffer.getvalue()

    def is_available(self) -> bool:
        """Check if the provider is ready for use.

        Returns:
            True if the model is loaded and ready.
        """
        return self._initialized and self._model is not None

    def shutdown(self) -> None:
        """Release provider resources."""
        if self._model is not None:
            # faster-whisper models don't need explicit cleanup
            self._model = None
            self._initialized = False
            logger.info("Local ASR provider shutdown")

    @property
    def name(self) -> str:
        """Get provider name."""
        return f"LocalASR(faster-whisper/{self._model_name})"

    @staticmethod
    def get_available_models() -> list[str]:
        """Get list of available Whisper models.

        Returns:
            List of model names.
        """
        return list(WHISPER_MODELS)

    @staticmethod
    def is_library_available() -> bool:
        """Check if faster-whisper library is installed.

        Returns:
            True if faster-whisper is available.
        """
        return FASTER_WHISPER_AVAILABLE

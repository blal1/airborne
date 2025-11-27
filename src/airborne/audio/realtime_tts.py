"""Real-time TTS generation for on-the-fly speech synthesis.

This module provides a TTS generator that works around pyttsx3's bug where
reusing engine instances produces corrupted files on macOS.

Supports two modes:
1. File-based: Generate WAV files (default, for caching)
2. Memory-based: Generate PCM samples directly for FMOD playback

Typical usage:
    from airborne.audio.realtime_tts import RealtimeTTS

    # File-based (for caching)
    tts = RealtimeTTS()
    wav_path = tts.generate("Runway three one, cleared for takeoff")

    # Memory-based (for direct FMOD playback)
    tts = RealtimeTTS()
    pcm_data = tts.generate_pcm("Cleared for takeoff")
    # pcm_data is a TTSAudioData with samples, sample_rate, channels, etc.
"""

import io
import logging
import platform
import struct
import tempfile
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TTSAudioData:
    """Raw audio data from TTS generation.

    Attributes:
        samples: Raw PCM samples as numpy array (int16).
        sample_rate: Sample rate in Hz (typically 22050 or 44100).
        channels: Number of audio channels (1=mono, 2=stereo).
        duration: Duration in seconds.
    """

    samples: np.ndarray
    sample_rate: int
    channels: int
    duration: float

    @property
    def bytes(self) -> bytes:
        """Get raw PCM bytes (int16, little-endian)."""
        return self.samples.tobytes()

    @property
    def num_samples(self) -> int:
        """Get total number of samples."""
        return len(self.samples)


class RealtimeTTS:
    """Real-time TTS generator for on-the-fly speech synthesis.

    Creates a new pyttsx3 engine instance for each generation to work around
    the macOS NSSpeechSynthesizer bug where reusing engines produces corrupted files.

    Attributes:
        rate: Speech rate in words per minute.
        voice_name: Voice name to use (platform-specific).
        output_dir: Directory for generated WAV files.

    Examples:
        >>> tts = RealtimeTTS(rate=180)
        >>> wav_path = tts.generate("Hello, world!")
        >>> print(wav_path)  # /tmp/tts_xxx/msg_0.wav
    """

    def __init__(
        self,
        rate: int = 180,
        voice_name: str | None = None,
        output_dir: Path | None = None,
        cache_enabled: bool = True,
    ) -> None:
        """Initialize real-time TTS generator.

        Args:
            rate: Speech rate in words per minute (default: 180).
            voice_name: Voice name to use. If None, uses system default.
            output_dir: Directory for output files. If None, uses temp directory.
            cache_enabled: If True, cache generated files by text hash.
        """
        self.rate = rate
        self.voice_name = voice_name
        self.cache_enabled = cache_enabled
        self._generation_count = 0
        self._lock = threading.Lock()
        self._cache: dict[str, Path] = {}
        self._pcm_cache: dict[str, TTSAudioData] = {}
        self._bytes_cache: dict[str, tuple[bytes, str]] = {}

        # Set up output directory
        if output_dir:
            self.output_dir = Path(output_dir)
            self.output_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.output_dir = Path(tempfile.mkdtemp(prefix="tts_"))

        logger.info(
            "RealtimeTTS initialized: rate=%d, voice=%s, output=%s",
            rate,
            voice_name or "default",
            self.output_dir,
        )

    def generate(self, text: str) -> Path | None:
        """Generate speech from text.

        Creates a WAV file containing the synthesized speech.

        Args:
            text: Text to convert to speech.

        Returns:
            Path to generated WAV file, or None if generation failed.
        """
        # Check cache first
        cache_key = self._get_cache_key(text)
        if self.cache_enabled and cache_key in self._cache:
            cached_path = self._cache[cache_key]
            if cached_path.exists():
                logger.debug("Cache hit for: %s", text[:30])
                return cached_path

        # Generate new file
        with self._lock:
            self._generation_count += 1
            output_path = self.output_dir / f"tts_{self._generation_count:06d}.wav"

        try:
            import pyttsx3

            # IMPORTANT: Create a new engine instance for EACH generation
            # This works around the macOS NSSpeechSynthesizer bug where
            # reusing engines produces corrupted WAV files after first use.
            engine = pyttsx3.init()
            engine.setProperty("rate", self.rate)

            # Set voice if specified
            if self.voice_name:
                voices = engine.getProperty("voices")
                for voice in voices:
                    if self.voice_name.lower() in voice.name.lower():
                        engine.setProperty("voice", voice.id)
                        break

            # Generate audio
            engine.save_to_file(text, str(output_path))
            engine.runAndWait()
            engine.stop()

            # Verify output
            if output_path.exists() and output_path.stat().st_size > 4096:
                # Cache successful generation
                if self.cache_enabled:
                    self._cache[cache_key] = output_path
                logger.debug("Generated TTS: %s -> %s", text[:30], output_path.name)
                return output_path
            else:
                logger.warning("TTS generation produced empty/corrupted file for: %s", text[:30])
                if output_path.exists():
                    output_path.unlink()
                return None

        except ImportError:
            logger.error("pyttsx3 not installed. Run: pip install pyttsx3")
            return None
        except Exception as e:
            logger.error("TTS generation failed for '%s': %s", text[:30], e)
            return None

    def generate_pcm(self, text: str) -> TTSAudioData | None:
        """Generate speech and return raw PCM samples in memory.

        This method generates TTS to a temporary file, reads it into memory,
        and returns the raw PCM data suitable for direct FMOD playback.

        Note: On macOS, pyttsx3 produces compressed AIFC files which require
        ffmpeg or another decoder. Consider using generate_audio_bytes() instead,
        which returns the raw file bytes for FMOD to decode directly.

        Args:
            text: Text to convert to speech.

        Returns:
            TTSAudioData containing raw PCM samples, or None if failed.

        Examples:
            >>> tts = RealtimeTTS()
            >>> audio = tts.generate_pcm("Hello world")
            >>> if audio:
            ...     print(f"Got {audio.num_samples} samples at {audio.sample_rate}Hz")
        """
        # Check PCM cache
        cache_key = self._get_cache_key(text) + "_pcm"
        if self.cache_enabled and cache_key in self._pcm_cache:
            logger.debug("PCM cache hit for: %s", text[:30])
            return self._pcm_cache[cache_key]

        # Generate to a temp file (reuse single temp path for efficiency)
        temp_path = self._get_temp_wav_path()

        try:
            import pyttsx3

            # Create new engine instance (workaround for macOS bug)
            engine = pyttsx3.init()
            engine.setProperty("rate", self.rate)

            if self.voice_name:
                voices = engine.getProperty("voices")
                for voice in voices:
                    if self.voice_name.lower() in voice.name.lower():
                        engine.setProperty("voice", voice.id)
                        break

            # Generate to temp file
            engine.save_to_file(text, str(temp_path))
            engine.runAndWait()
            engine.stop()

            # Read WAV into memory immediately
            if not temp_path.exists() or temp_path.stat().st_size <= 4096:
                logger.warning("TTS generation failed for: %s", text[:30])
                return None

            audio_data = self._read_audio_to_pcm(temp_path)

            # Cache the PCM data
            if audio_data and self.cache_enabled:
                self._pcm_cache[cache_key] = audio_data

            logger.debug(
                "Generated PCM: %s -> %d samples @ %dHz",
                text[:30],
                audio_data.num_samples if audio_data else 0,
                audio_data.sample_rate if audio_data else 0,
            )
            return audio_data

        except ImportError:
            logger.error("pyttsx3 not installed")
            return None
        except Exception as e:
            logger.error("TTS PCM generation failed: %s", e)
            return None
        finally:
            # Clean up temp file
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    def generate_audio_bytes(self, text: str) -> tuple[bytes, str] | None:
        """Generate speech and return WAV audio bytes.

        This is the recommended method for FMOD playback. Always returns WAV
        format for cross-platform compatibility (converts AIFF to WAV on macOS).

        Args:
            text: Text to convert to speech.

        Returns:
            Tuple of (wav_bytes, 'wav') or None if failed.

        Examples:
            >>> tts = RealtimeTTS()
            >>> result = tts.generate_audio_bytes("Hello world")
            >>> if result:
            ...     audio_bytes, fmt = result
            ...     sound = fmod_engine.load_sound_from_bytes(audio_bytes)
        """
        # Check bytes cache
        cache_key = self._get_cache_key(text) + "_bytes"
        if self.cache_enabled and cache_key in self._bytes_cache:
            logger.debug("Bytes cache hit for: %s", text[:30])
            return self._bytes_cache[cache_key]

        # Generate to a temp file
        temp_path = self._get_temp_wav_path()
        wav_path = temp_path.with_suffix(".converted.wav")

        try:
            import pyttsx3

            # Create new engine instance (workaround for macOS bug)
            engine = pyttsx3.init()
            engine.setProperty("rate", self.rate)

            if self.voice_name:
                voices = engine.getProperty("voices")
                for voice in voices:
                    if self.voice_name.lower() in voice.name.lower():
                        engine.setProperty("voice", voice.id)
                        break

            # Generate to temp file
            engine.save_to_file(text, str(temp_path))
            engine.runAndWait()
            engine.stop()

            # Check output
            if not temp_path.exists() or temp_path.stat().st_size <= 4096:
                logger.warning("TTS generation failed for: %s", text[:30])
                return None

            # Check format and convert if needed
            with open(temp_path, "rb") as f:
                header = f.read(4)

            if header == b"RIFF":
                # Already WAV, read directly
                with open(temp_path, "rb") as f:
                    audio_bytes = f.read()
            elif header == b"FORM":
                # AIFF/AIFC - convert to WAV using ffmpeg
                audio_bytes = self._convert_to_wav(temp_path, wav_path)
                if audio_bytes is None:
                    logger.error("Failed to convert AIFF to WAV for: %s", text[:30])
                    return None
            else:
                logger.warning("Unknown audio format: %s", header)
                return None

            result = (audio_bytes, "wav")

            # Cache
            if self.cache_enabled:
                self._bytes_cache[cache_key] = result

            logger.debug(
                "Generated audio bytes: %s -> %d bytes (wav)",
                text[:30],
                len(audio_bytes),
            )
            return result

        except ImportError:
            logger.error("pyttsx3 not installed")
            return None
        except Exception as e:
            logger.error("TTS bytes generation failed: %s", e)
            return None
        finally:
            # Clean up temp files
            for path in [temp_path, wav_path]:
                if path.exists():
                    try:
                        path.unlink()
                    except OSError:
                        pass

    def _convert_to_wav(self, input_path: Path, output_path: Path) -> bytes | None:
        """Convert audio file to WAV format using ffmpeg.

        Args:
            input_path: Path to input audio file (AIFF, etc.).
            output_path: Path for output WAV file.

        Returns:
            WAV file bytes, or None if conversion failed.
        """
        import subprocess

        try:
            # Use ffmpeg to convert to WAV (PCM s16le)
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    str(input_path),
                    "-acodec",
                    "pcm_s16le",
                    "-ar",
                    "22050",
                    "-ac",
                    "1",
                    "-y",
                    str(output_path),
                ],
                capture_output=True,
                check=True,
            )

            if output_path.exists():
                with open(output_path, "rb") as f:
                    return f.read()
            return None

        except subprocess.CalledProcessError as e:
            logger.error("ffmpeg conversion failed: %s", e.stderr.decode()[:200])
            return None
        except FileNotFoundError:
            logger.error("ffmpeg not found - required for AIFF to WAV conversion on macOS")
            return None

    def _get_temp_wav_path(self) -> Path:
        """Get path for temporary WAV file.

        Uses a single temp file path per thread to minimize disk operations.
        """
        thread_id = threading.current_thread().ident
        return self.output_dir / f"_temp_{thread_id}.wav"

    def _read_audio_to_pcm(self, audio_path: Path) -> TTSAudioData | None:
        """Read an audio file (WAV or AIFF) into PCM samples.

        Supports both WAV and AIFF formats (pyttsx3 produces AIFF on macOS).

        Args:
            audio_path: Path to audio file.

        Returns:
            TTSAudioData or None if reading failed.
        """
        try:
            # Detect format by reading header
            with open(audio_path, "rb") as f:
                header = f.read(4)

            if header == b"RIFF":
                return self._read_wav_file(audio_path)
            elif header == b"FORM":
                return self._read_aiff_file(audio_path)
            else:
                logger.warning("Unknown audio format: %s", header[:4])
                return None

        except Exception as e:
            logger.error("Failed to read audio file %s: %s", audio_path, e)
            return None

    def _read_wav_file(self, wav_path: Path) -> TTSAudioData | None:
        """Read a WAV file into PCM samples."""
        try:
            with wave.open(str(wav_path), "rb") as wf:
                channels = wf.getnchannels()
                sample_rate = wf.getframerate()
                sample_width = wf.getsampwidth()
                n_frames = wf.getnframes()
                raw_data = wf.readframes(n_frames)

            return self._convert_pcm_data(raw_data, sample_width, sample_rate, channels, n_frames)

        except Exception as e:
            logger.error("Failed to read WAV file %s: %s", wav_path, e)
            return None

    def _read_aiff_file(self, aiff_path: Path) -> TTSAudioData | None:
        """Read an AIFF/AIFC file into PCM samples.

        macOS pyttsx3 produces AIFC (compressed AIFF) files.
        """
        import aifc

        try:
            with aifc.open(str(aiff_path), "rb") as af:
                channels = af.getnchannels()
                sample_rate = af.getframerate()
                sample_width = af.getsampwidth()
                n_frames = af.getnframes()
                raw_data = af.readframes(n_frames)

            # AIFF uses big-endian, need to convert to little-endian for numpy
            return self._convert_pcm_data(
                raw_data, sample_width, sample_rate, channels, n_frames, big_endian=True
            )

        except Exception as e:
            logger.error("Failed to read AIFF file %s: %s", aiff_path, e)
            return None

    def _convert_pcm_data(
        self,
        raw_data: bytes,
        sample_width: int,
        sample_rate: int,
        channels: int,
        n_frames: int,
        big_endian: bool = False,
    ) -> TTSAudioData | None:
        """Convert raw PCM bytes to TTSAudioData.

        Args:
            raw_data: Raw PCM bytes.
            sample_width: Bytes per sample (1, 2, or 4).
            sample_rate: Sample rate in Hz.
            channels: Number of channels.
            n_frames: Number of frames.
            big_endian: If True, data is big-endian (AIFF format).

        Returns:
            TTSAudioData or None if conversion failed.
        """
        try:
            # Determine dtype based on sample width and endianness
            if sample_width == 1:
                # 8-bit unsigned
                samples = np.frombuffer(raw_data, dtype=np.uint8).astype(np.int16)
                samples = (samples - 128) * 256
            elif sample_width == 2:
                # 16-bit signed
                if big_endian:
                    samples = np.frombuffer(raw_data, dtype=">i2").astype(np.int16)
                else:
                    samples = np.frombuffer(raw_data, dtype=np.int16)
            elif sample_width == 4:
                # 32-bit signed -> convert to int16
                if big_endian:
                    samples = np.frombuffer(raw_data, dtype=">i4")
                else:
                    samples = np.frombuffer(raw_data, dtype=np.int32)
                samples = (samples // 65536).astype(np.int16)
            else:
                logger.warning("Unsupported sample width: %d", sample_width)
                return None

            duration = n_frames / sample_rate

            return TTSAudioData(
                samples=samples,
                sample_rate=sample_rate,
                channels=channels,
                duration=duration,
            )

        except Exception as e:
            logger.error("Failed to convert PCM data: %s", e)
            return None

    def generate_async(
        self,
        text: str,
        callback: Callable[[Path | None], None],
    ) -> None:
        """Generate speech asynchronously.

        Args:
            text: Text to convert to speech.
            callback: Function called with result path (or None on failure).
        """
        def _generate():
            result = self.generate(text)
            callback(result)

        thread = threading.Thread(target=_generate, daemon=True)
        thread.start()

    def _get_cache_key(self, text: str) -> str:
        """Get cache key for text.

        Args:
            text: Text to hash.

        Returns:
            Cache key string.
        """
        import hashlib

        # Include rate and voice in cache key
        key_data = f"{self.rate}:{self.voice_name or 'default'}:{text}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def clear_cache(self) -> int:
        """Clear the generation cache and delete cached files.

        Returns:
            Number of files deleted.
        """
        count = 0
        for path in self._cache.values():
            if path.exists():
                path.unlink()
                count += 1
        self._cache.clear()
        self._pcm_cache.clear()
        self._bytes_cache.clear()
        logger.info("Cleared TTS cache: %d files", count)
        return count

    def cleanup(self) -> None:
        """Clean up all generated files and reset state."""
        self.clear_cache()

        # Delete any remaining files in output directory
        for wav_file in self.output_dir.glob("tts_*.wav"):
            wav_file.unlink()

        self._generation_count = 0
        logger.info("TTS cleanup complete")


class TTSQueue:
    """Queue-based TTS generator for batch processing.

    Processes TTS requests in a background thread with rate limiting.

    Examples:
        >>> queue = TTSQueue()
        >>> queue.start()
        >>> queue.enqueue("Message one", callback=on_ready)
        >>> queue.enqueue("Message two", callback=on_ready)
        >>> # ... later ...
        >>> queue.stop()
    """

    def __init__(
        self,
        rate: int = 180,
        voice_name: str | None = None,
        max_queue_size: int = 100,
    ) -> None:
        """Initialize TTS queue.

        Args:
            rate: Speech rate in words per minute.
            voice_name: Voice name to use.
            max_queue_size: Maximum pending requests.
        """
        import queue

        self.tts = RealtimeTTS(rate=rate, voice_name=voice_name)
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the TTS processing thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
        logger.info("TTS queue started")

    def stop(self) -> None:
        """Stop the TTS processing thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("TTS queue stopped")

    def enqueue(
        self,
        text: str,
        callback: Callable[[Path | None], None] | None = None,
        priority: int = 0,
    ) -> bool:
        """Add a TTS request to the queue.

        Args:
            text: Text to convert to speech.
            callback: Optional callback with result path.
            priority: Request priority (lower = higher priority).

        Returns:
            True if enqueued, False if queue is full.
        """
        try:
            self._queue.put_nowait((priority, text, callback))
            return True
        except Exception:
            logger.warning("TTS queue full, dropping request: %s", text[:30])
            return False

    def _process_loop(self) -> None:
        """Background thread processing loop."""
        while self._running:
            try:
                # Get next request with timeout
                try:
                    priority, text, callback = self._queue.get(timeout=0.5)
                except Exception:
                    continue

                # Generate TTS
                result = self.tts.generate(text)

                # Call callback if provided
                if callback:
                    try:
                        callback(result)
                    except Exception as e:
                        logger.error("TTS callback error: %s", e)

                self._queue.task_done()

            except Exception as e:
                logger.error("TTS queue error: %s", e)

    def cleanup(self) -> None:
        """Stop queue and clean up resources."""
        self.stop()
        self.tts.cleanup()

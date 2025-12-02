"""Persistent TTS cache manager with background generation.

This module provides a disk-based cache for TTS audio files that persists
across sessions. It supports background generation of common phrases while
prioritizing user requests.

Architecture:
    - Disk cache in ~/.airborne/tts_cache/{voice}/
    - Manifest file tracks cached items with metadata
    - Background thread generates priority items
    - User requests interrupt background and get immediate service

Typical usage:
    from airborne.audio.tts.cache_manager import TTSCacheManager

    cache = TTSCacheManager(voice="cockpit", rate=180)
    cache.start_background_generation()

    # User request - returns cached or generates immediately
    audio_bytes = cache.get_audio("120")  # Cache hit: ~5ms, miss: ~350ms

    # Shutdown
    cache.shutdown()
"""

import hashlib
import json
import logging
import platform
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Metadata for a cached TTS audio file.

    Attributes:
        text: Original text that was synthesized.
        filename: Name of the WAV file in cache directory.
        created_at: Unix timestamp when file was created.
        voice_settings: Dict of voice settings (rate, voice_name).
        file_size: Size of the WAV file in bytes.
    """

    text: str
    filename: str
    created_at: float
    voice_settings: dict[str, Any]
    file_size: int = 0


@dataclass
class GenerationPriority:
    """Priority levels for background generation.

    Lower values = higher priority (generated first).
    """

    IMMEDIATE: int = 0  # User request - not queued, generated now
    STARTUP: int = 1  # Numbers 0-999, common words
    GROUND_OPS: int = 2  # Numbers 1000-5000, low flight levels
    CRUISE: int = 3  # Numbers 5000-20000
    HIGH_ALT: int = 4  # Numbers 20000-40000


@dataclass
class QueueItem:
    """Item in the background generation queue.

    Attributes:
        text: Text to synthesize.
        priority: Generation priority (lower = higher priority).
        added_at: Unix timestamp when added to queue.
    """

    text: str
    priority: int = GenerationPriority.STARTUP
    added_at: float = field(default_factory=time.time)

    def __lt__(self, other: "QueueItem") -> bool:
        """Compare by priority for heap operations."""
        return self.priority < other.priority


class TTSCacheManager:
    """Manages persistent TTS cache with background generation.

    Provides disk-based caching of TTS audio files that persists across
    sessions. Background thread generates common phrases while user
    requests are always prioritized.

    Attributes:
        voice: Voice identifier (e.g., "cockpit", "tower").
        rate: Speech rate in words per minute.
        voice_name: Platform-specific voice name.
        cache_dir: Path to cache directory.

    Examples:
        >>> cache = TTSCacheManager(voice="cockpit", rate=180)
        >>> cache.start_background_generation()
        >>> audio = cache.get_audio("altitude")
        >>> cache.shutdown()
    """

    # Cache location (same base as settings: ~/.airborne on Mac/Linux, %USERPROFILE%\.airborne on Windows)
    DEFAULT_CACHE_BASE = Path.home() / ".airborne" / "tts_cache"

    # Manifest filename
    MANIFEST_FILE = "manifest.json"

    def __init__(
        self,
        voice: str = "cockpit",
        rate: int = 180,
        voice_name: str | None = None,
        cache_base: Path | None = None,
    ) -> None:
        """Initialize TTS cache manager.

        Args:
            voice: Voice identifier for subdirectory (e.g., "cockpit", "tower").
            rate: Speech rate in words per minute.
            voice_name: Platform-specific voice name (None = system default).
            cache_base: Base cache directory. If None, uses ~/.airborne/tts_cache/.
        """
        self.voice = voice
        self.rate = rate
        self.voice_name = voice_name

        # Setup cache directory
        base = cache_base or self.DEFAULT_CACHE_BASE
        self.cache_dir = base / voice
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Load or create manifest
        self._manifest: dict[str, CacheEntry] = {}
        self._manifest_path = self.cache_dir / self.MANIFEST_FILE
        self._load_manifest()

        # Background generation state
        self._queue: deque[QueueItem] = deque()
        self._queued_texts: set[str] = set()  # For O(1) lookup
        self._in_progress: str | None = None
        self._completed: set[str] = set()  # Generated this session
        self._lock = threading.Lock()
        self._user_request = threading.Event()  # Signals user request in progress
        self._shutdown_event = threading.Event()
        self._background_thread: threading.Thread | None = None

        # Statistics
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "background_generated": 0,
            "user_generated": 0,
        }

        logger.info(
            "TTSCacheManager initialized: voice=%s, rate=%d, cache_dir=%s, cached_items=%d",
            voice,
            rate,
            self.cache_dir,
            len(self._manifest),
        )

    def _load_manifest(self) -> None:
        """Load manifest from disk."""
        if not self._manifest_path.exists():
            logger.info("No existing manifest, starting fresh")
            return

        try:
            with open(self._manifest_path, encoding="utf-8") as f:
                data = json.load(f)

            # Convert to CacheEntry objects
            for hash_key, entry_data in data.get("entries", {}).items():
                # Validate file exists
                filepath = self.cache_dir / entry_data["filename"]
                if filepath.exists():
                    self._manifest[hash_key] = CacheEntry(
                        text=entry_data["text"],
                        filename=entry_data["filename"],
                        created_at=entry_data["created_at"],
                        voice_settings=entry_data["voice_settings"],
                        file_size=entry_data.get("file_size", 0),
                    )
                else:
                    logger.debug("Cache file missing, skipping: %s", filepath)

            logger.info("Loaded manifest with %d valid entries", len(self._manifest))

        except Exception as e:
            logger.error("Error loading manifest: %s", e)
            self._manifest = {}

    def _save_manifest(self) -> None:
        """Save manifest to disk."""
        try:
            data = {
                "version": 1,
                "voice": self.voice,
                "entries": {
                    hash_key: {
                        "text": entry.text,
                        "filename": entry.filename,
                        "created_at": entry.created_at,
                        "voice_settings": entry.voice_settings,
                        "file_size": entry.file_size,
                    }
                    for hash_key, entry in self._manifest.items()
                },
            }

            # Write atomically
            temp_path = self._manifest_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_path.replace(self._manifest_path)

        except Exception as e:
            logger.error("Error saving manifest: %s", e)

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key from text and voice settings.

        Args:
            text: Text to hash.

        Returns:
            Hash string that uniquely identifies this text + settings combo.
        """
        # Include voice settings in hash so cache invalidates if settings change
        key_data = f"{self.rate}:{self.voice_name or 'default'}:{text}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def _get_voice_settings(self) -> dict[str, Any]:
        """Get current voice settings dict."""
        return {
            "rate": self.rate,
            "voice_name": self.voice_name,
            "platform": platform.system(),
        }

    def get_audio(self, text: str) -> bytes | None:
        """Get audio bytes for text, from cache or generated.

        This is the main entry point for TTS. It checks the cache first,
        and if not found, generates immediately (interrupting background).

        Args:
            text: Text to synthesize.

        Returns:
            WAV audio bytes, or None if generation failed.

        Note:
            User requests always take priority over background generation.
        """
        if not text or not text.strip():
            return None

        cache_key = self._get_cache_key(text)

        # Check cache
        with self._lock:
            if cache_key in self._manifest:
                entry = self._manifest[cache_key]
                filepath = self.cache_dir / entry.filename
                if filepath.exists():
                    self._stats["cache_hits"] += 1
                    logger.debug("Cache hit: %s", text[:30])
                    return filepath.read_bytes()
                else:
                    # File was deleted, remove from manifest
                    del self._manifest[cache_key]

            # Cache miss - remove from background queue if present
            if text in self._queued_texts:
                self._queued_texts.discard(text)
                # Note: item stays in deque but will be skipped when processed

        # Signal background thread to pause
        self._user_request.set()

        try:
            # Generate immediately
            self._stats["cache_misses"] += 1
            self._stats["user_generated"] += 1
            logger.debug("Cache miss, generating: %s", text[:30])

            audio_bytes = self._generate_and_cache(text, cache_key)
            return audio_bytes

        finally:
            # Resume background thread
            self._user_request.clear()

    def _generate_and_cache(self, text: str, cache_key: str) -> bytes | None:
        """Generate TTS audio and save to cache.

        Args:
            text: Text to synthesize.
            cache_key: Pre-computed cache key.

        Returns:
            WAV audio bytes, or None if generation failed.
        """
        import tempfile

        # Generate to temp file first
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            aiff_path = temp_path / "output.aiff"
            wav_path = temp_path / "output.wav"

            # Step 1: Generate with pyttsx3
            try:
                import pyttsx3

                engine = pyttsx3.init()
                engine.setProperty("rate", self.rate)

                if self.voice_name:
                    voices = engine.getProperty("voices")
                    for v in voices:
                        if self.voice_name.lower() in v.name.lower():
                            engine.setProperty("voice", v.id)
                            break

                engine.save_to_file(text, str(aiff_path))
                engine.runAndWait()
                engine.stop()
                del engine

            except Exception as e:
                logger.error("pyttsx3 generation failed: %s", e)
                return None

            # Check output exists
            if not aiff_path.exists() or aiff_path.stat().st_size < 100:
                logger.error("pyttsx3 produced no output for: %s", text[:30])
                return None

            # Step 2: Convert AIFF to WAV with ffmpeg
            try:
                result = subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(aiff_path),
                        "-acodec",
                        "pcm_s16le",
                        "-ar",
                        "22050",
                        "-ac",
                        "1",
                        str(wav_path),
                    ],
                    capture_output=True,
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                logger.error("ffmpeg conversion failed: %s", e.stderr.decode()[:200])
                return None
            except FileNotFoundError:
                logger.error("ffmpeg not found - required for TTS")
                return None

            if not wav_path.exists():
                logger.error("ffmpeg produced no output")
                return None

            # Read WAV bytes
            audio_bytes = wav_path.read_bytes()

            # Validate WAV has actual audio content (not just header)
            # A valid WAV with audio should be > 100 bytes minimum
            if len(audio_bytes) < 500:
                logger.warning(
                    "Generated WAV too small (%d bytes) for: %s - likely empty audio",
                    len(audio_bytes),
                    text[:30],
                )
                return None

            # Save to cache
            cache_filename = f"{cache_key}.wav"
            cache_filepath = self.cache_dir / cache_filename

            try:
                cache_filepath.write_bytes(audio_bytes)

                # Update manifest
                with self._lock:
                    self._manifest[cache_key] = CacheEntry(
                        text=text,
                        filename=cache_filename,
                        created_at=time.time(),
                        voice_settings=self._get_voice_settings(),
                        file_size=len(audio_bytes),
                    )
                    self._completed.add(text)

                # Save manifest periodically (every 10 items)
                if len(self._completed) % 10 == 0:
                    self._save_manifest()

                logger.debug(
                    "Cached: %s -> %s (%d bytes)",
                    text[:30],
                    cache_filename,
                    len(audio_bytes),
                )

            except Exception as e:
                logger.error("Failed to save to cache: %s", e)
                # Still return the audio even if caching failed

            return audio_bytes

    def is_cached(self, text: str) -> bool:
        """Check if text is already cached.

        Args:
            text: Text to check.

        Returns:
            True if cached and file exists.
        """
        cache_key = self._get_cache_key(text)
        with self._lock:
            if cache_key in self._manifest:
                filepath = self.cache_dir / self._manifest[cache_key].filename
                return filepath.exists()
        return False

    def queue_for_generation(self, text: str, priority: int = GenerationPriority.STARTUP) -> bool:
        """Add text to background generation queue.

        Args:
            text: Text to generate.
            priority: Generation priority (lower = higher).

        Returns:
            True if queued, False if already cached/queued.
        """
        if not text or not text.strip():
            return False

        # Skip if already cached
        if self.is_cached(text):
            return False

        with self._lock:
            # Skip if already queued or completed this session
            if text in self._queued_texts or text in self._completed:
                return False

            self._queue.append(QueueItem(text=text, priority=priority))
            self._queued_texts.add(text)

        return True

    def queue_priority_items(self) -> int:
        """Queue standard priority items for background generation.

        Queues numbers 0-999, common words, and flight levels based on
        priority tiers.

        Returns:
            Number of items queued.
        """
        queued = 0

        # Priority 1: Numbers 0-999 (most common for instruments)
        for i in range(1000):
            if self.queue_for_generation(str(i), GenerationPriority.STARTUP):
                queued += 1

        # Priority 1: Common aviation words
        common_words = [
            "heading",
            "altitude",
            "airspeed",
            "knots",
            "feet",
            "degrees",
            "flight level",
            "runway",
            "cleared",
            "taxi",
            "takeoff",
            "landing",
            "approach",
            "departure",
            "tower",
            "ground",
            "center",
            "radio",
            "squawk",
            "ident",
            "contact",
            "frequency",
            "maintain",
            "climb",
            "descend",
            "turn",
            "left",
            "right",
            "direct",
            "hold",
            "short",
            "position",
            "line up",
            "wait",
            "go around",
            "missed approach",
            "traffic",
            "in sight",
            "negative",
            "affirmative",
            "wilco",
            "roger",
            "unable",
            "standby",
            "say again",
            "correction",
            # Phonetic alphabet
            "alpha",
            "bravo",
            "charlie",
            "delta",
            "echo",
            "foxtrot",
            "golf",
            "hotel",
            "india",
            "juliet",
            "kilo",
            "lima",
            "mike",
            "november",
            "oscar",
            "papa",
            "quebec",
            "romeo",
            "sierra",
            "tango",
            "uniform",
            "victor",
            "whiskey",
            "xray",
            "yankee",
            "zulu",
            # Number words
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "niner",
            "ten",
            "eleven",
            "twelve",
            "hundred",
            "thousand",
            "decimal",
            "point",
        ]
        for word in common_words:
            if self.queue_for_generation(word, GenerationPriority.STARTUP):
                queued += 1

        # Priority 2: Numbers 1000-5000 (pattern/low altitude)
        for i in range(1000, 5001):
            if self.queue_for_generation(str(i), GenerationPriority.GROUND_OPS):
                queued += 1

        # Priority 2: Low flight levels
        for fl in range(10, 151):
            text = f"flight level {fl:03d}"
            if self.queue_for_generation(text, GenerationPriority.GROUND_OPS):
                queued += 1

        # Priority 3: Numbers 5000-20000 (cruise)
        for i in range(5001, 20001):
            if self.queue_for_generation(str(i), GenerationPriority.CRUISE):
                queued += 1

        # Priority 3: Mid flight levels
        for fl in range(151, 301):
            text = f"flight level {fl:03d}"
            if self.queue_for_generation(text, GenerationPriority.CRUISE):
                queued += 1

        # Priority 4: Numbers 20000-40000 (high altitude)
        for i in range(20001, 40001):
            if self.queue_for_generation(str(i), GenerationPriority.HIGH_ALT):
                queued += 1

        # Priority 4: High flight levels
        for fl in range(301, 451):
            text = f"flight level {fl:03d}"
            if self.queue_for_generation(text, GenerationPriority.HIGH_ALT):
                queued += 1

        logger.info("Queued %d items for background generation", queued)
        return queued

    def start_background_generation(self) -> None:
        """Start background generation thread."""
        if self._background_thread and self._background_thread.is_alive():
            logger.warning("Background generation already running")
            return

        self._shutdown_event.clear()
        self._background_thread = threading.Thread(
            target=self._background_generation_loop,
            name="TTS-CacheGenerator",
            daemon=True,
        )
        self._background_thread.start()
        logger.info("Background generation thread started")

    def _background_generation_loop(self) -> None:
        """Background thread loop for generating queued items."""
        logger.info("Background generation loop started")

        while not self._shutdown_event.is_set():
            # Wait if user request in progress
            while self._user_request.is_set():
                if self._shutdown_event.is_set():
                    return
                time.sleep(0.01)

            # Get next item
            item = None
            with self._lock:
                while self._queue:
                    candidate = self._queue.popleft()
                    # Skip if already completed or removed from queue
                    if (
                        candidate.text not in self._completed
                        and candidate.text in self._queued_texts
                    ):
                        item = candidate
                        self._queued_texts.discard(candidate.text)
                        self._in_progress = candidate.text
                        break
                    self._queued_texts.discard(candidate.text)

            if not item:
                # Queue empty, wait a bit and check again
                time.sleep(0.5)
                continue

            # Check if already cached (might have been user-generated)
            if self.is_cached(item.text):
                with self._lock:
                    self._completed.add(item.text)
                    self._in_progress = None
                continue

            # Generate
            try:
                cache_key = self._get_cache_key(item.text)
                self._generate_and_cache(item.text, cache_key)
                self._stats["background_generated"] += 1

                # Log progress periodically
                if self._stats["background_generated"] % 100 == 0:
                    logger.info(
                        "Background generation progress: %d items, queue size: %d",
                        self._stats["background_generated"],
                        len(self._queue),
                    )

            except Exception as e:
                logger.error("Background generation error for '%s': %s", item.text, e)

            finally:
                with self._lock:
                    self._in_progress = None

            # Delay between generations to allow pyttsx3/NSSpeechSynthesizer cleanup
            # Without this delay, rapid successive calls can produce empty audio
            time.sleep(0.1)

        logger.info("Background generation loop ended")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with cache hits, misses, generation counts.
        """
        with self._lock:
            return {
                **self._stats,
                "cached_items": len(self._manifest),
                "queue_size": len(self._queue),
                "in_progress": self._in_progress,
            }

    def get_cache_size_bytes(self) -> int:
        """Get total size of cached files in bytes."""
        total = 0
        for entry in self._manifest.values():
            total += entry.file_size
        return total

    def clear_cache(self) -> int:
        """Clear all cached files.

        Returns:
            Number of files deleted.
        """
        count = 0
        with self._lock:
            for entry in self._manifest.values():
                filepath = self.cache_dir / entry.filename
                if filepath.exists():
                    filepath.unlink()
                    count += 1
            self._manifest.clear()
            self._completed.clear()
            self._save_manifest()

        logger.info("Cleared cache: %d files deleted", count)
        return count

    def shutdown(self) -> None:
        """Shutdown cache manager and save state."""
        logger.info("Shutting down TTSCacheManager")

        # Stop background thread
        self._shutdown_event.set()
        if self._background_thread and self._background_thread.is_alive():
            self._background_thread.join(timeout=2.0)

        # Save manifest
        self._save_manifest()

        logger.info(
            "TTSCacheManager shutdown complete. Stats: %s",
            self.get_stats(),
        )

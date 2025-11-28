"""Disk cache management for TTS Cache Service.

This module provides disk-based caching of TTS audio files organized by
voice settings. Each unique combination of settings gets its own directory.

Cache structure:
    ~/.cache/airborne/tts/
    ├── a1b2c3d4/          # hash of {rate:180, voice:"Samantha"}
    │   ├── manifest.json
    │   └── *.wav
    ├── e5f6g7h8/          # hash of {rate:200, voice:"Alex"}
    │   ├── manifest.json
    │   └── *.wav
"""

import hashlib
import json
import logging
import platform
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Metadata for a cached TTS audio file."""

    text: str
    filename: str
    created_at: float
    last_accessed: float
    file_size: int = 0


@dataclass
class VoiceSettings:
    """Voice settings that determine cache directory.

    Attributes:
        voice: Logical voice name (e.g., "cockpit", "tower", "atis").
        rate: Speech rate in words per minute.
        voice_name: Platform-specific voice name (e.g., "Samantha", "Alex").
    """

    voice: str = "cockpit"
    rate: int = 180
    voice_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "voice": self.voice,
            "rate": self.rate,
            "voice_name": self.voice_name,
            "platform": platform.system(),
        }

    def get_hash(self) -> str:
        """Get hash string for these settings."""
        key = f"{self.voice}:{self.rate}:{self.voice_name or 'default'}:{platform.system()}"
        return hashlib.sha256(key.encode()).hexdigest()[:12]


class TTSDiskCache:
    """Manages disk-based TTS cache with settings-based directories.

    Each unique voice settings combination gets its own subdirectory.
    Supports LRU cleanup with configurable grace period.
    """

    DEFAULT_CACHE_BASE = Path.home() / ".cache" / "airborne" / "tts"
    MANIFEST_FILE = "manifest.json"
    SETTINGS_FILE = "settings.json"

    def __init__(
        self,
        settings: VoiceSettings,
        cache_base: Path | None = None,
    ) -> None:
        """Initialize disk cache.

        Args:
            settings: Voice settings determining cache directory.
            cache_base: Base cache directory. If None, uses default.
        """
        self.settings = settings
        self.cache_base = cache_base or self.DEFAULT_CACHE_BASE
        self.cache_base.mkdir(parents=True, exist_ok=True)

        # Current cache directory based on settings hash
        self.settings_hash = settings.get_hash()
        self.cache_dir = self.cache_base / self.settings_hash
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Manifest tracks cached items
        self._manifest: dict[str, CacheEntry] = {}
        self._manifest_path = self.cache_dir / self.MANIFEST_FILE
        self._load_manifest()

        # Save settings for reference
        self._save_settings()

        # Statistics
        self._stats = {
            "hits": 0,
            "misses": 0,
            "generated": 0,
        }

        logger.info(
            "TTSDiskCache initialized: hash=%s, dir=%s, items=%d",
            self.settings_hash,
            self.cache_dir,
            len(self._manifest),
        )

    def _load_manifest(self) -> None:
        """Load manifest from disk."""
        if not self._manifest_path.exists():
            return

        try:
            with open(self._manifest_path, encoding="utf-8") as f:
                data = json.load(f)

            for text_hash, entry_data in data.get("entries", {}).items():
                filepath = self.cache_dir / entry_data["filename"]
                if filepath.exists():
                    self._manifest[text_hash] = CacheEntry(
                        text=entry_data["text"],
                        filename=entry_data["filename"],
                        created_at=entry_data["created_at"],
                        last_accessed=entry_data.get("last_accessed", entry_data["created_at"]),
                        file_size=entry_data.get("file_size", 0),
                    )

            logger.info("Loaded manifest: %d entries", len(self._manifest))

        except Exception as e:
            logger.error("Error loading manifest: %s", e)
            self._manifest = {}

    def _save_manifest(self) -> None:
        """Save manifest to disk."""
        try:
            data = {
                "version": 1,
                "settings_hash": self.settings_hash,
                "entries": {
                    text_hash: {
                        "text": entry.text,
                        "filename": entry.filename,
                        "created_at": entry.created_at,
                        "last_accessed": entry.last_accessed,
                        "file_size": entry.file_size,
                    }
                    for text_hash, entry in self._manifest.items()
                },
            }

            temp_path = self._manifest_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_path.replace(self._manifest_path)

        except Exception as e:
            logger.error("Error saving manifest: %s", e)

    def _save_settings(self) -> None:
        """Save current settings to cache directory."""
        settings_path = self.cache_dir / self.SETTINGS_FILE
        try:
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(self.settings.to_dict(), f, indent=2)
        except Exception as e:
            logger.error("Error saving settings: %s", e)

    def _get_text_hash(self, text: str) -> str:
        """Get hash for text content."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def get(self, text: str) -> bytes | None:
        """Get cached audio for text.

        Args:
            text: Text to look up.

        Returns:
            WAV bytes if cached, None otherwise.
        """
        text_hash = self._get_text_hash(text)

        if text_hash not in self._manifest:
            self._stats["misses"] += 1
            return None

        entry = self._manifest[text_hash]
        filepath = self.cache_dir / entry.filename

        if not filepath.exists():
            del self._manifest[text_hash]
            self._stats["misses"] += 1
            return None

        # Update last accessed time
        entry.last_accessed = time.time()
        self._stats["hits"] += 1

        return filepath.read_bytes()

    def put(self, text: str, audio_bytes: bytes) -> bool:
        """Store audio in cache.

        Args:
            text: Text that was synthesized.
            audio_bytes: WAV audio data.

        Returns:
            True if stored successfully.
        """
        if len(audio_bytes) < 500:
            logger.warning("Audio too small to cache: %d bytes", len(audio_bytes))
            return False

        text_hash = self._get_text_hash(text)
        filename = f"{text_hash}.wav"
        filepath = self.cache_dir / filename

        try:
            filepath.write_bytes(audio_bytes)

            self._manifest[text_hash] = CacheEntry(
                text=text,
                filename=filename,
                created_at=time.time(),
                last_accessed=time.time(),
                file_size=len(audio_bytes),
            )

            self._stats["generated"] += 1

            # Save manifest periodically
            if self._stats["generated"] % 10 == 0:
                self._save_manifest()

            return True

        except Exception as e:
            logger.error("Error caching audio: %s", e)
            return False

    def contains(self, text: str) -> bool:
        """Check if text is cached."""
        text_hash = self._get_text_hash(text)
        if text_hash not in self._manifest:
            return False
        filepath = self.cache_dir / self._manifest[text_hash].filename
        return filepath.exists()

    def generate(self, text: str) -> bytes | None:
        """Generate TTS audio using pyttsx3.

        Args:
            text: Text to synthesize.

        Returns:
            WAV audio bytes, or None if failed.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            aiff_path = temp_path / "output.aiff"
            wav_path = temp_path / "output.wav"

            try:
                import pyttsx3

                engine = pyttsx3.init()
                engine.setProperty("rate", self.settings.rate)

                if self.settings.voice_name:
                    voices = engine.getProperty("voices")
                    for v in voices:
                        if self.settings.voice_name.lower() in v.name.lower():
                            engine.setProperty("voice", v.id)
                            break

                engine.save_to_file(text, str(aiff_path))
                engine.runAndWait()
                engine.stop()
                del engine

            except Exception as e:
                logger.error("pyttsx3 generation failed: %s", e)
                return None

            if not aiff_path.exists() or aiff_path.stat().st_size < 100:
                logger.error("pyttsx3 produced no output for: %s", text[:30])
                return None

            # Convert AIFF to WAV
            try:
                subprocess.run(
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
                logger.error("ffmpeg failed: %s", e.stderr.decode()[:200])
                return None
            except FileNotFoundError:
                logger.error("ffmpeg not found")
                return None

            if not wav_path.exists():
                return None

            audio_bytes = wav_path.read_bytes()

            if len(audio_bytes) < 500:
                logger.warning("Generated audio too small: %d bytes", len(audio_bytes))
                return None

            return audio_bytes

    def get_or_generate(self, text: str) -> tuple[bytes | None, bool]:
        """Get from cache or generate.

        Args:
            text: Text to synthesize.

        Returns:
            Tuple of (audio_bytes, was_cached).
        """
        # Try cache first
        audio = self.get(text)
        if audio:
            return audio, True

        # Generate
        audio = self.generate(text)
        if audio:
            self.put(text, audio)
            return audio, False

        return None, False

    def switch_settings(self, new_settings: VoiceSettings) -> str:
        """Switch to new voice settings.

        Args:
            new_settings: New voice settings.

        Returns:
            New settings hash.
        """
        # Save current manifest
        self._save_manifest()

        # Update settings
        self.settings = new_settings
        self.settings_hash = new_settings.get_hash()
        self.cache_dir = self.cache_base / self.settings_hash
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Load new manifest
        self._manifest = {}
        self._manifest_path = self.cache_dir / self.MANIFEST_FILE
        self._load_manifest()

        # Save settings
        self._save_settings()

        logger.info("Switched to settings: hash=%s", self.settings_hash)
        return self.settings_hash

    def cleanup_lru(self, grace_period_days: int = 2) -> int:
        """Clean up least recently used items across all cache directories.

        Args:
            grace_period_days: Don't delete items accessed within this period.

        Returns:
            Number of items deleted.
        """
        deleted = 0
        cutoff_time = time.time() - (grace_period_days * 24 * 60 * 60)

        # Iterate all cache directories
        for settings_dir in self.cache_base.iterdir():
            if not settings_dir.is_dir():
                continue

            # Skip current active directory
            if settings_dir.name == self.settings_hash:
                continue

            manifest_path = settings_dir / self.MANIFEST_FILE
            if not manifest_path.exists():
                continue

            try:
                with open(manifest_path, encoding="utf-8") as f:
                    data = json.load(f)

                entries = data.get("entries", {})
                entries_to_delete = []

                for text_hash, entry_data in entries.items():
                    last_accessed = entry_data.get("last_accessed", entry_data.get("created_at", 0))
                    if last_accessed < cutoff_time:
                        # Delete file
                        filepath = settings_dir / entry_data["filename"]
                        if filepath.exists():
                            filepath.unlink()
                            deleted += 1
                        entries_to_delete.append(text_hash)

                # Update manifest
                for text_hash in entries_to_delete:
                    del entries[text_hash]

                # Save updated manifest
                if entries_to_delete:
                    with open(manifest_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)

                # Remove empty directories
                if not entries:
                    for file_path in settings_dir.iterdir():
                        file_path.unlink()
                    settings_dir.rmdir()
                    logger.info("Removed empty cache directory: %s", settings_dir.name)

            except Exception as e:
                logger.error("Error cleaning up %s: %s", settings_dir.name, e)

        if deleted > 0:
            logger.info("LRU cleanup: deleted %d items", deleted)

        return deleted

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_size = sum(e.file_size for e in self._manifest.values())
        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "generated": self._stats["generated"],
            "cached_items": len(self._manifest),
            "cache_size_mb": total_size / 1024 / 1024,
            "settings_hash": self.settings_hash,
        }

    def save(self) -> None:
        """Save manifest to disk."""
        self._save_manifest()

"""Direct TTS cache access - fallback when WebSocket service is unavailable.

This module provides direct access to cached TTS files on disk, bypassing
the WebSocket service entirely. Used as a fallback when the TTS cache service
fails to start.

Typical usage:
    cache = DirectTTSCache()
    audio = cache.get_cached_audio("Main Menu", voice_name="Samantha", rate=200)
    if audio:
        play_audio(audio)
"""

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DirectTTSCache:
    """Direct access to TTS cache files on disk.
    
    This class provides a simple fallback mechanism to load pre-generated
    TTS files directly from the cache directory when the WebSocket service
    is not available.
    """
    
    DEFAULT_CACHE_BASE = Path.home() / ".airborne" / "tts_cache"
    
    def __init__(self, cache_base: Path | None = None) -> None:
        """Initialize direct TTS cache access.
        
        Args:
            cache_base: Base cache directory. If None, uses default.
        """
        self.cache_base = cache_base or self.DEFAULT_CACHE_BASE
        self._cache_dirs: dict[str, Path] = {}
        self._scan_cache_directories()
        
        total_files = sum(len(list(d.glob("*.wav"))) for d in self._cache_dirs.values())
        logger.info(
            "DirectTTSCache initialized: %d cache directories, %d cached files",
            len(self._cache_dirs),
            total_files
        )
    
    def _scan_cache_directories(self) -> None:
        """Scan cache base for existing cache directories."""
        if not self.cache_base.exists():
            logger.warning("TTS cache directory does not exist: %s", self.cache_base)
            return
        
        for cache_dir in self.cache_base.iterdir():
            if not cache_dir.is_dir():
                continue
            
            # Load settings to identify this cache
            settings_file = cache_dir / "settings.json"
            manifest_file = cache_dir / "manifest.json"
            
            if settings_file.exists() and manifest_file.exists():
                try:
                    with open(settings_file, encoding="utf-8") as f:
                        settings = json.load(f)
                    
                    # Create key from settings
                    voice_name = settings.get("voice_name", "default")
                    rate = settings.get("rate", 180)
                    language = settings.get("language", "default")
                    
                    key = f"{voice_name}:{rate}:{language}"
                    self._cache_dirs[key] = cache_dir
                    
                    logger.debug(
                        "Found cache dir: %s (%s files)",
                        cache_dir.name,
                        len(list(cache_dir.glob("*.wav")))
                    )
                except Exception as e:
                    logger.debug("Skipping cache dir %s: %s", cache_dir.name, e)
    
    def _get_text_hash(self, text: str) -> str:
        """Get hash for text content (matches cache.py implementation)."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]
    
    def _find_cache_dir(self, voice_name: str | None = None, rate: int = 180, language: str | None = None) -> Path | None:
        """Find the best matching cache directory.
        
        Args:
            voice_name: Voice name to match.
            rate: Speech rate to match.
            language: Language to match.
            
        Returns:
            Path to cache directory or None if not found.
        """
        # Try exact match first
        key = f"{voice_name or 'default'}:{rate}:{language or 'default'}"
        if key in self._cache_dirs:
            return self._cache_dirs[key]
        
        # Try without language
        key_no_lang = f"{voice_name or 'default'}:{rate}:default"
        if key_no_lang in self._cache_dirs:
            return self._cache_dirs[key_no_lang]
        
        # Try first available directory as last resort
        if self._cache_dirs:
            return next(iter(self._cache_dirs.values()))
        
        return None
    
    def get_cached_audio(
        self,
        text: str,
        voice_name: str | None = None,
        rate: int = 180,
        language: str | None = None
    ) -> bytes | None:
        """Get cached audio for text.
        
        Args:
            text: Text to look up.
            voice_name: Voice name to match.
            rate: Speech rate in WPM.
            language: Language code.
            
        Returns:
            WAV audio bytes if cached, None otherwise.
        """
        if not text:
            return None
        
        # Find matching cache directory
        cache_dir = self._find_cache_dir(voice_name, rate, language)
        if not cache_dir:
            logger.debug("No cache directory found for voice=%s, rate=%d", voice_name, rate)
            return None
        
        # Load manifest
        manifest_file = cache_dir / "manifest.json"
        if not manifest_file.exists():
            logger.debug("No manifest found in %s", cache_dir)
            return None
        
        try:
            with open(manifest_file, encoding="utf-8") as f:
                manifest_data = json.load(f)
            
            # Look up text hash
            text_hash = self._get_text_hash(text)
            entries = manifest_data.get("entries", {})
            
            if text_hash not in entries:
                logger.debug("Text not in cache: %s", text[:30])
                return None
            
            # Load audio file
            entry = entries[text_hash]
            filename = entry.get("filename")
            if not filename:
                logger.debug("No filename in manifest entry")
                return None
            
            audio_file = cache_dir / filename
            if not audio_file.exists():
                logger.debug("Audio file not found: %s", audio_file)
                return None
            
            audio_bytes = audio_file.read_bytes()
            logger.debug("Loaded cached audio: %s (%d bytes)", text[:30], len(audio_bytes))
            return audio_bytes
            
        except Exception as e:
            logger.error("Failed to load cached audio: %s", e)
            return None
    
    def has_cache(self) -> bool:
        """Check if any cache directories exist."""
        return len(self._cache_dirs) > 0

"""JSON IPC protocol definitions for TTS Cache Service.

This module defines the request/response message types for communication
between Airborne and the TTS Cache Service subprocess via WebSocket.

Protocol:
    - All messages are JSON
    - Binary data (WAV bytes) is base64 encoded in the response
    - Request format: {"cmd": "...", "id": "...", ...}
    - Response format: {"id": "...", "ok": true/false, ...}

WebSocket endpoint: ws://127.0.0.1:51127 (configurable)

Example exchange:
    >>> {"cmd": "generate", "id": "abc123", "text": "altitude 3500"}
    <<< {"id": "abc123", "ok": true, "size": 69902, "cached": false, "data": "<base64>"}
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Request:
    """Base request message."""

    cmd: str
    id: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {"cmd": self.cmd, "id": self.id}


@dataclass
class GenerateRequest(Request):
    """Request to generate TTS audio.

    Attributes:
        text: Text to synthesize.
        voice: Voice name for cache organization (e.g., "cockpit", "tower").
        rate: Speech rate in words per minute.
        voice_name: Platform-specific voice name (e.g., "Samantha", "Alex").
        priority: Generation priority (lower = higher priority).
    """

    text: str
    voice: str = "cockpit"
    rate: int = 180
    voice_name: str | None = None
    priority: int = 0
    cmd: str = field(default="generate", init=False)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "cmd": self.cmd,
            "id": self.id,
            "text": self.text,
            "voice": self.voice,
            "rate": self.rate,
            "priority": self.priority,
        }
        if self.voice_name:
            d["voice_name"] = self.voice_name
        return d


@dataclass
class InvalidateRequest(Request):
    """Request to invalidate queue and switch TTS settings.

    Attributes:
        rate: New speech rate in words per minute.
        voice_name: New voice name (platform-specific).
    """

    rate: int
    voice_name: str | None = None
    cmd: str = field(default="invalidate", init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cmd": self.cmd,
            "id": self.id,
            "rate": self.rate,
            "voice_name": self.voice_name,
        }


@dataclass
class QueueRequest(Request):
    """Request to queue items for background generation.

    Attributes:
        texts: List of texts to queue for generation.
        voice: Voice name for cache organization (e.g., "cockpit", "tower").
        rate: Speech rate in words per minute.
        voice_name: Platform-specific voice name (e.g., "Samantha", "Alex").
        priority: Generation priority for all items.
    """

    texts: list[str] = field(default_factory=list)
    voice: str = "cockpit"
    rate: int = 180
    voice_name: str | None = None
    priority: int = 1
    cmd: str = field(default="queue", init=False)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "cmd": self.cmd,
            "id": self.id,
            "texts": self.texts,
            "voice": self.voice,
            "rate": self.rate,
            "priority": self.priority,
        }
        if self.voice_name:
            d["voice_name"] = self.voice_name
        return d


@dataclass
class PingRequest(Request):
    """Health check ping request."""

    cmd: str = field(default="ping", init=False)


@dataclass
class StatsRequest(Request):
    """Request cache statistics."""

    cmd: str = field(default="stats", init=False)


@dataclass
class ShutdownRequest(Request):
    """Request graceful shutdown."""

    cmd: str = field(default="shutdown", init=False)


@dataclass
class ContextRequest(Request):
    """Request to set the current flight context for pre-generation.

    The service uses context to prioritize what items to pre-generate:
    - "menu": Main menu, minimal pre-generation
    - "ground": On ground, pre-generate taxi/takeoff phrases
    - "airborne": In flight, pre-generate altitude/heading/speed phrases

    Attributes:
        context: Current flight context ("menu", "ground", "airborne").
        voices: Dict of voice configs {voice_name: {rate, voice_name}} for pre-gen.
    """

    context: str
    voices: dict[str, dict[str, Any]] = field(default_factory=dict)
    cmd: str = field(default="context", init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cmd": self.cmd,
            "id": self.id,
            "context": self.context,
            "voices": self.voices,
        }


@dataclass
class Response:
    """Base response message."""

    id: str
    ok: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d: dict[str, Any] = {"id": self.id, "ok": self.ok}
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class GenerateResponse(Response):
    """Response to generate request.

    Attributes:
        size: Size of WAV data in bytes (0 if failed).
        cached: True if served from cache, False if generated.
        duration_ms: Generation time in milliseconds.
        data: Base64-encoded WAV audio data.
    """

    size: int = 0
    cached: bool = False
    duration_ms: float = 0.0
    data: str = ""  # Base64-encoded WAV

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update(
            {
                "size": self.size,
                "cached": self.cached,
                "duration_ms": self.duration_ms,
                "data": self.data,
            }
        )
        return d


@dataclass
class InvalidateResponse(Response):
    """Response to invalidate request.

    Attributes:
        cleared_queue: Number of items cleared from queue.
        new_settings_hash: Hash of new settings directory.
    """

    cleared_queue: int = 0
    new_settings_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update(
            {
                "cleared_queue": self.cleared_queue,
                "new_settings_hash": self.new_settings_hash,
            }
        )
        return d


@dataclass
class QueueResponse(Response):
    """Response to queue request.

    Attributes:
        queued: Number of items actually queued (excludes already cached).
        skipped: Number of items skipped (already cached).
    """

    queued: int = 0
    skipped: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({"queued": self.queued, "skipped": self.skipped})
        return d


@dataclass
class PingResponse(Response):
    """Response to ping request.

    Attributes:
        uptime_s: Service uptime in seconds.
        queue_size: Current generation queue size.
    """

    uptime_s: float = 0.0
    queue_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({"uptime_s": self.uptime_s, "queue_size": self.queue_size})
        return d


@dataclass
class StatsResponse(Response):
    """Response to stats request.

    Attributes:
        cache_hits: Number of cache hits.
        cache_misses: Number of cache misses.
        generated: Total items generated this session.
        cached_items: Total items in current cache directory.
        queue_size: Current generation queue size.
        cache_size_mb: Total cache size in MB.
        settings_hash: Current settings hash.
    """

    cache_hits: int = 0
    cache_misses: int = 0
    generated: int = 0
    cached_items: int = 0
    queue_size: int = 0
    cache_size_mb: float = 0.0
    settings_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update(
            {
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "generated": self.generated,
                "cached_items": self.cached_items,
                "queue_size": self.queue_size,
                "cache_size_mb": self.cache_size_mb,
                "settings_hash": self.settings_hash,
            }
        )
        return d


@dataclass
class ContextResponse(Response):
    """Response to context request.

    Attributes:
        context: The context that was set.
        queued: Number of items queued for pre-generation.
    """

    context: str = ""
    queued: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({"context": self.context, "queued": self.queued})
        return d


def parse_request(data: dict[str, Any]) -> Request | None:
    """Parse a request dictionary into a Request object.

    Args:
        data: Dictionary from JSON parsing.

    Returns:
        Request object or None if invalid.
    """
    cmd = data.get("cmd")
    req_id = data.get("id", "")

    if cmd == "generate":
        return GenerateRequest(
            id=req_id,
            text=data.get("text", ""),
            voice=data.get("voice", "cockpit"),
            rate=data.get("rate", 180),
            voice_name=data.get("voice_name"),
            priority=data.get("priority", 0),
        )
    elif cmd == "invalidate":
        return InvalidateRequest(
            id=req_id,
            rate=data.get("rate", 180),
            voice_name=data.get("voice_name"),
        )
    elif cmd == "queue":
        return QueueRequest(
            id=req_id,
            texts=data.get("texts", []),
            voice=data.get("voice", "cockpit"),
            rate=data.get("rate", 180),
            voice_name=data.get("voice_name"),
            priority=data.get("priority", 1),
        )
    elif cmd == "ping":
        return PingRequest(id=req_id)
    elif cmd == "stats":
        return StatsRequest(id=req_id)
    elif cmd == "shutdown":
        return ShutdownRequest(id=req_id)
    elif cmd == "context":
        return ContextRequest(
            id=req_id,
            context=data.get("context", "menu"),
            voices=data.get("voices", {}),
        )
    else:
        return None


def parse_response(data: dict[str, Any]) -> Response:
    """Parse a response dictionary into a Response object.

    Args:
        data: Dictionary from JSON parsing.

    Returns:
        Response object.
    """
    # Determine response type based on fields present
    if "size" in data and "data" in data:
        return GenerateResponse(
            id=data.get("id", ""),
            ok=data.get("ok", False),
            error=data.get("error"),
            size=data.get("size", 0),
            cached=data.get("cached", False),
            duration_ms=data.get("duration_ms", 0.0),
            data=data.get("data", ""),
        )
    elif "cleared_queue" in data:
        return InvalidateResponse(
            id=data.get("id", ""),
            ok=data.get("ok", False),
            error=data.get("error"),
            cleared_queue=data.get("cleared_queue", 0),
            new_settings_hash=data.get("new_settings_hash", ""),
        )
    elif "queued" in data:
        return QueueResponse(
            id=data.get("id", ""),
            ok=data.get("ok", False),
            error=data.get("error"),
            queued=data.get("queued", 0),
            skipped=data.get("skipped", 0),
        )
    elif "uptime_s" in data:
        return PingResponse(
            id=data.get("id", ""),
            ok=data.get("ok", False),
            error=data.get("error"),
            uptime_s=data.get("uptime_s", 0.0),
            queue_size=data.get("queue_size", 0),
        )
    elif "cache_hits" in data:
        return StatsResponse(
            id=data.get("id", ""),
            ok=data.get("ok", False),
            error=data.get("error"),
            cache_hits=data.get("cache_hits", 0),
            cache_misses=data.get("cache_misses", 0),
            generated=data.get("generated", 0),
            cached_items=data.get("cached_items", 0),
            queue_size=data.get("queue_size", 0),
            cache_size_mb=data.get("cache_size_mb", 0.0),
            settings_hash=data.get("settings_hash", ""),
        )
    elif "context" in data and "queued" in data:
        return ContextResponse(
            id=data.get("id", ""),
            ok=data.get("ok", False),
            error=data.get("error"),
            context=data.get("context", ""),
            queued=data.get("queued", 0),
        )
    else:
        return Response(
            id=data.get("id", ""),
            ok=data.get("ok", False),
            error=data.get("error"),
        )

#!/usr/bin/env python3
"""TTS Cache Service health check script.

This script probes the TTS Cache Service WebSocket endpoint to verify
it's running and responsive.

Usage:
    python scripts/tts_healthcheck.py [options]

Options:
    --host HOST     WebSocket host (default: 127.0.0.1)
    --port PORT     WebSocket port (default: 51127)
    --verbose       Show detailed output
    --stats         Show cache statistics
    --generate TEXT Test generation with given text

Exit codes:
    0 - Service is healthy
    1 - Service is not responding
    2 - Connection error
"""

import argparse
import asyncio
import json
import sys
import time

try:
    import websockets
    from websockets.client import connect
except ImportError:
    print("ERROR: websockets package required. Install with: pip install websockets")
    sys.exit(2)


async def ping_service(host: str, port: int, timeout: float = 5.0) -> dict | None:
    """Ping the service and return response."""
    url = f"ws://{host}:{port}"
    try:
        async with connect(url) as ws:
            request = {"cmd": "ping", "id": "healthcheck"}
            await ws.send(json.dumps(request))
            response = await asyncio.wait_for(ws.recv(), timeout=timeout)
            return json.loads(response)
    except Exception as e:
        return {"error": str(e)}


async def get_stats(host: str, port: int, timeout: float = 5.0) -> dict | None:
    """Get cache statistics."""
    url = f"ws://{host}:{port}"
    try:
        async with connect(url) as ws:
            request = {"cmd": "stats", "id": "stats"}
            await ws.send(json.dumps(request))
            response = await asyncio.wait_for(ws.recv(), timeout=timeout)
            return json.loads(response)
    except Exception as e:
        return {"error": str(e)}


async def test_generate(host: str, port: int, text: str, timeout: float = 30.0) -> dict | None:
    """Test TTS generation."""
    url = f"ws://{host}:{port}"
    try:
        async with connect(url) as ws:
            request = {"cmd": "generate", "id": "test", "text": text}
            await ws.send(json.dumps(request))
            response = await asyncio.wait_for(ws.recv(), timeout=timeout)
            return json.loads(response)
    except Exception as e:
        return {"error": str(e)}


async def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="TTS Cache Service health check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="WebSocket host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=51127,
        help="WebSocket port (default: 51127)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show cache statistics",
    )
    parser.add_argument(
        "--generate",
        metavar="TEXT",
        help="Test generation with given text",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Request timeout in seconds (default: 5)",
    )

    args = parser.parse_args()

    url = f"ws://{args.host}:{args.port}"

    if args.verbose:
        print(f"Checking TTS Cache Service at {url}...")

    # Ping check
    start_time = time.time()
    response = await ping_service(args.host, args.port, args.timeout)
    elapsed = (time.time() - start_time) * 1000

    if response is None or "error" in response:
        error = response.get("error", "Unknown error") if response else "No response"
        print(f"UNHEALTHY: {error}")
        return 2

    if not response.get("ok"):
        print(f"UNHEALTHY: {response.get('error', 'Service returned error')}")
        return 1

    # Basic health OK
    uptime = response.get("uptime_s", 0)
    queue_size = response.get("queue_size", 0)

    if args.verbose:
        print(f"HEALTHY: uptime={uptime:.1f}s, queue={queue_size}, latency={elapsed:.1f}ms")
    else:
        print(f"OK (uptime: {uptime:.0f}s)")

    # Stats if requested
    if args.stats:
        stats = await get_stats(args.host, args.port, args.timeout)
        if stats and stats.get("ok"):
            print("\nCache Statistics:")
            print(f"  Hits:         {stats.get('cache_hits', 0)}")
            print(f"  Misses:       {stats.get('cache_misses', 0)}")
            print(f"  Generated:    {stats.get('generated', 0)}")
            print(f"  Cached items: {stats.get('cached_items', 0)}")
            print(f"  Queue size:   {stats.get('queue_size', 0)}")
            print(f"  Cache size:   {stats.get('cache_size_mb', 0):.2f} MB")
            print(f"  Settings:     {stats.get('settings_hash', 'N/A')}")

    # Test generation if requested
    if args.generate:
        print(f"\nTesting generation: '{args.generate}'")
        start_time = time.time()
        gen_response = await test_generate(args.host, args.port, args.generate, timeout=30.0)
        gen_elapsed = (time.time() - start_time) * 1000

        if gen_response and gen_response.get("ok"):
            size = gen_response.get("size", 0)
            cached = gen_response.get("cached", False)
            duration = gen_response.get("duration_ms", 0)
            source = "cache" if cached else "generated"
            print(f"  Result: {size} bytes ({source})")
            print(f"  Server time: {duration:.1f}ms")
            print(f"  Total time:  {gen_elapsed:.1f}ms")
        else:
            error = gen_response.get("error", "Unknown error") if gen_response else "No response"
            print(f"  Failed: {error}")

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

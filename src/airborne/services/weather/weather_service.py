"""Weather service for aviation weather data.

Provides real METAR data from APIs with simulated fallback.
Supports background thread fetching for non-blocking startup.
"""

import threading
from datetime import UTC, datetime
from typing import Any

import aiohttp
import requests

from airborne.core.logging_system import get_logger
from airborne.services.weather.metar_parser import METARParser
from airborne.services.weather.models import Weather
from airborne.services.weather.weather_simulator import WeatherSimulator

logger = get_logger(__name__)


class WeatherService:
    """Service for fetching and managing aviation weather data.

    Attempts to fetch real METAR data from online APIs, falling back
    to simulated weather when real data is unavailable.

    Attributes:
        cache_duration: How long to cache weather data (default 5 minutes).
        use_real_weather: Whether to attempt fetching real METAR data.
    """

    # METAR API endpoints (in priority order)
    METAR_APIS = [
        # CheckWX API (requires API key, but has free tier)
        # "https://api.checkwx.com/metar/{icao}/decoded",
        # Aviation Weather Center (NOAA) - free, no API key required
        "https://aviationweather.gov/api/data/metar?ids={icao}&format=raw",
    ]

    def __init__(
        self,
        cache_duration: float = 300.0,
        use_real_weather: bool = True,
        api_timeout: float = 5.0,
    ):
        """Initialize weather service.

        Args:
            cache_duration: Cache duration in seconds (default 5 minutes).
            use_real_weather: Whether to try fetching real METAR data.
            api_timeout: Timeout for API requests in seconds.
        """
        self.cache_duration = cache_duration
        self.use_real_weather = use_real_weather
        self.api_timeout = api_timeout

        self._parser = METARParser()
        self._simulator = WeatherSimulator(update_interval=cache_duration)
        self._cache: dict[str, tuple[Weather, datetime]] = {}
        self._session: aiohttp.ClientSession | None = None

        # Background fetch tracking
        self._fetch_threads: dict[str, threading.Thread] = {}
        self._fetch_lock = threading.Lock()

    async def get_weather(self, icao: str) -> Weather:
        """Get weather for an airport.

        Tries to fetch real METAR data, falls back to simulated weather.

        Args:
            icao: Airport ICAO code (e.g., "KPAO", "KSFO").

        Returns:
            Weather object (real or simulated).
        """
        icao = icao.upper()

        # Check cache first
        cached = self._get_cached(icao)
        if cached is not None:
            return cached

        # Try to fetch real METAR
        weather = None
        if self.use_real_weather:
            weather = await self._fetch_metar(icao)

        # Fall back to simulated weather
        if weather is None:
            logger.debug("Using simulated weather for %s", icao)
            weather = self._simulator.generate(icao)

        # Cache the result
        self._cache[icao] = (weather, datetime.now(UTC))

        return weather

    def get_weather_sync(self, icao: str) -> Weather:
        """Synchronous version of get_weather.

        Returns cached real METAR if available (from background fetch),
        otherwise falls back to simulated weather.

        Args:
            icao: Airport ICAO code.

        Returns:
            Weather object (from cache or simulated).
        """
        icao = icao.upper()

        # Check cache first (may contain real METAR from background fetch)
        cached = self._get_cached(icao)
        if cached is not None:
            return cached

        # Generate simulated weather (synchronous)
        weather = self._simulator.generate(icao)
        self._cache[icao] = (weather, datetime.now(UTC))

        return weather

    def prefetch_weather(self, icao: str) -> None:
        """Start background fetch of real METAR data.

        Spawns a thread to fetch METAR from APIs. The result is cached
        so subsequent calls to get_weather_sync() will return real data.

        Args:
            icao: Airport ICAO code to prefetch.
        """
        if not self.use_real_weather:
            return

        icao = icao.upper()

        with self._fetch_lock:
            # Don't start duplicate fetches
            if icao in self._fetch_threads:
                thread = self._fetch_threads[icao]
                if thread.is_alive():
                    logger.debug("Background fetch already in progress for %s", icao)
                    return

            # Start background fetch thread
            thread = threading.Thread(
                target=self._fetch_metar_thread,
                args=(icao,),
                name=f"metar-fetch-{icao}",
                daemon=True,
            )
            self._fetch_threads[icao] = thread
            thread.start()
            logger.info("Started background METAR fetch for %s", icao)

    def _fetch_metar_thread(self, icao: str) -> None:
        """Background thread worker for fetching METAR.

        Args:
            icao: Airport ICAO code.
        """
        try:
            weather = self._fetch_metar_sync(icao)
            if weather:
                with self._fetch_lock:
                    self._cache[icao] = (weather, datetime.now(UTC))
                logger.info("Background METAR fetch succeeded for %s", icao)
            else:
                logger.debug("Background METAR fetch returned no data for %s", icao)
        except Exception as e:
            logger.warning("Background METAR fetch failed for %s: %s", icao, e)

    def _fetch_metar_sync(self, icao: str) -> Weather | None:
        """Fetch METAR data synchronously using requests.

        Args:
            icao: Airport ICAO code.

        Returns:
            Weather object from METAR, or None if fetch failed.
        """
        for api_url in self.METAR_APIS:
            try:
                url = api_url.format(icao=icao)
                response = requests.get(url, timeout=self.api_timeout)
                if response.status_code == 200:
                    metar_text = response.text.strip()
                    if metar_text:
                        weather = self._parser.parse(metar_text)
                        if weather:
                            logger.info("Fetched real METAR for %s: %s", icao, metar_text)
                            return weather
            except requests.Timeout:
                logger.debug("METAR API request timed out: %s", api_url)
                continue
            except requests.RequestException as e:
                logger.debug("METAR API request failed: %s - %s", api_url, e)
                continue

        return None

    def wait_for_prefetch(self, icao: str, timeout: float = 5.0) -> bool:
        """Wait for a background prefetch to complete.

        Args:
            icao: Airport ICAO code.
            timeout: Maximum time to wait in seconds.

        Returns:
            True if prefetch completed, False if timed out or not started.
        """
        icao = icao.upper()

        with self._fetch_lock:
            thread = self._fetch_threads.get(icao)
            if thread is None:
                return False

        thread.join(timeout=timeout)
        return not thread.is_alive()

    def _get_cached(self, icao: str) -> Weather | None:
        """Get cached weather if still valid.

        Args:
            icao: Airport ICAO code.

        Returns:
            Cached Weather object, or None if not cached or expired.
        """
        if icao not in self._cache:
            return None

        weather, cached_time = self._cache[icao]
        age = (datetime.now(UTC) - cached_time).total_seconds()

        if age < self.cache_duration:
            return weather

        return None

    async def _fetch_metar(self, icao: str) -> Weather | None:
        """Fetch real METAR data from APIs.

        Args:
            icao: Airport ICAO code.

        Returns:
            Weather object from METAR, or None if fetch failed.
        """
        for api_url in self.METAR_APIS:
            try:
                url = api_url.format(icao=icao)
                metar_text = await self._fetch_url(url)
                if metar_text:
                    weather = self._parser.parse(metar_text)
                    if weather:
                        logger.info("Fetched real METAR for %s: %s", icao, metar_text.strip())
                        return weather
            except Exception as e:
                logger.warning("Failed to fetch METAR from %s: %s", api_url, e)
                continue

        logger.debug("No real METAR available for %s", icao)
        return None

    async def _fetch_url(self, url: str) -> str | None:
        """Fetch content from URL.

        Args:
            url: URL to fetch.

        Returns:
            Response text, or None if fetch failed.
        """
        try:
            if self._session is None:
                self._session = aiohttp.ClientSession()

            async with self._session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=self.api_timeout),
            ) as response:
                if response.status == 200:
                    return await response.text()
                logger.debug("METAR API returned status %d for %s", response.status, url)
                return None
        except TimeoutError:
            logger.debug("METAR API request timed out: %s", url)
            return None
        except aiohttp.ClientError as e:
            logger.debug("METAR API request failed: %s - %s", url, e)
            return None

    def invalidate_cache(self, icao: str | None = None) -> None:
        """Invalidate cached weather data.

        Args:
            icao: Airport ICAO code to invalidate, or None to clear all.
        """
        if icao is None:
            self._cache.clear()
            logger.debug("Cleared all weather cache")
        elif icao.upper() in self._cache:
            del self._cache[icao.upper()]
            logger.debug("Cleared weather cache for %s", icao)

    def get_cache_info(self) -> dict[str, Any]:
        """Get information about cached weather data.

        Returns:
            Dictionary with cache statistics.
        """
        now = datetime.now(UTC)
        entries = []
        for icao, (weather, cached_time) in self._cache.items():
            age = (now - cached_time).total_seconds()
            entries.append(
                {
                    "icao": icao,
                    "is_simulated": weather.is_simulated,
                    "age_seconds": age,
                    "expires_in": max(0, self.cache_duration - age),
                }
            )
        return {
            "count": len(self._cache),
            "cache_duration": self.cache_duration,
            "entries": entries,
        }

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    def __del__(self) -> None:
        """Cleanup on deletion."""
        if self._session and not self._session.closed:
            # Can't await in __del__, just warn
            logger.warning("WeatherService session not properly closed")

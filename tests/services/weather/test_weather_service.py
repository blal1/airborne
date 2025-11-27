"""Tests for weather service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from airborne.services.weather.models import Weather, Wind
from airborne.services.weather.weather_service import WeatherService


class TestWeatherService:
    """Tests for WeatherService class."""

    @pytest.fixture
    def service(self) -> WeatherService:
        """Create service fixture with real weather disabled."""
        return WeatherService(use_real_weather=False)

    @pytest.fixture
    def real_service(self) -> WeatherService:
        """Create service fixture with real weather enabled."""
        return WeatherService(use_real_weather=True, api_timeout=1.0)

    def test_sync_returns_weather(self, service: WeatherService) -> None:
        """Test synchronous weather retrieval."""
        weather = service.get_weather_sync("KPAO")
        assert weather is not None
        assert weather.icao == "KPAO"
        assert weather.is_simulated is True

    def test_sync_caches_weather(self, service: WeatherService) -> None:
        """Test that weather is cached."""
        weather1 = service.get_weather_sync("KPAO")
        weather2 = service.get_weather_sync("KPAO")

        # Should be the same cached object
        assert weather1 is weather2

    def test_sync_different_airports(self, service: WeatherService) -> None:
        """Test different airports get different weather."""
        weather_pao = service.get_weather_sync("KPAO")
        weather_sfo = service.get_weather_sync("KSFO")

        assert weather_pao.icao == "KPAO"
        assert weather_sfo.icao == "KSFO"

    def test_icao_normalized_to_uppercase(self, service: WeatherService) -> None:
        """Test that ICAO codes are normalized to uppercase."""
        weather1 = service.get_weather_sync("kpao")
        weather2 = service.get_weather_sync("KPAO")

        assert weather1.icao == "KPAO"
        assert weather1 is weather2

    def test_invalidate_cache_single(self, service: WeatherService) -> None:
        """Test invalidating cache for single airport."""
        weather1 = service.get_weather_sync("KPAO")
        service.invalidate_cache("KPAO")
        weather2 = service.get_weather_sync("KPAO")

        # Should be different objects after invalidation
        assert weather1 is not weather2

    def test_invalidate_cache_all(self, service: WeatherService) -> None:
        """Test invalidating all cached weather."""
        service.get_weather_sync("KPAO")
        service.get_weather_sync("KSFO")

        service.invalidate_cache()

        info = service.get_cache_info()
        assert info["count"] == 0

    def test_get_cache_info(self, service: WeatherService) -> None:
        """Test cache info retrieval."""
        service.get_weather_sync("KPAO")
        service.get_weather_sync("KSFO")

        info = service.get_cache_info()
        assert info["count"] == 2
        assert len(info["entries"]) == 2

    @pytest.mark.asyncio
    async def test_async_returns_weather(self, service: WeatherService) -> None:
        """Test asynchronous weather retrieval."""
        weather = await service.get_weather("KPAO")
        assert weather is not None
        assert weather.icao == "KPAO"

    @pytest.mark.asyncio
    async def test_async_caches_weather(self, service: WeatherService) -> None:
        """Test that async weather is cached."""
        weather1 = await service.get_weather("KPAO")
        weather2 = await service.get_weather("KPAO")

        assert weather1 is weather2

    @pytest.mark.asyncio
    async def test_close_session(self, service: WeatherService) -> None:
        """Test closing the HTTP session."""
        # Force session creation
        await service.get_weather("KPAO")
        await service.close()
        assert service._session is None

    @pytest.mark.asyncio
    async def test_fetch_metar_returns_real_weather(self, real_service: WeatherService) -> None:
        """Test METAR fetching with mocked response."""
        metar_text = "KPAO 251756Z 32008KT 10SM CLR 18/08 A3002"

        with patch.object(real_service, "_fetch_url", new_callable=AsyncMock) as mock:
            mock.return_value = metar_text

            weather = await real_service.get_weather("KPAO")

            assert weather is not None
            assert weather.icao == "KPAO"
            assert weather.is_simulated is False
            assert weather.raw_metar == metar_text

    @pytest.mark.asyncio
    async def test_fetch_failure_falls_back_to_simulated(
        self, real_service: WeatherService
    ) -> None:
        """Test that fetch failure falls back to simulated weather."""
        with patch.object(real_service, "_fetch_url", new_callable=AsyncMock) as mock:
            mock.return_value = None

            weather = await real_service.get_weather("KPAO")

            assert weather is not None
            assert weather.is_simulated is True

    @pytest.mark.asyncio
    async def test_invalid_metar_falls_back(self, real_service: WeatherService) -> None:
        """Test that invalid METAR falls back to simulated."""
        with patch.object(real_service, "_fetch_url", new_callable=AsyncMock) as mock:
            mock.return_value = "INVALID DATA"

            weather = await real_service.get_weather("KPAO")

            assert weather is not None
            assert weather.is_simulated is True

    def test_cache_expiry(self, service: WeatherService) -> None:
        """Test that cache entries expire."""
        # Use very short cache duration
        service = WeatherService(cache_duration=0.1, use_real_weather=False)

        weather1 = service.get_weather_sync("KPAO")

        import time

        time.sleep(0.2)

        # Should get new weather after expiry
        weather2 = service.get_weather_sync("KPAO")
        assert weather1 is not weather2

    def test_prefetch_starts_background_thread(self, real_service: WeatherService) -> None:
        """Test that prefetch starts a background thread."""
        with patch.object(real_service, "_fetch_metar_sync") as mock:
            mock.return_value = None

            real_service.prefetch_weather("KPAO")

            # Give thread time to start
            import time

            time.sleep(0.1)

            # Thread should have been started
            assert "KPAO" in real_service._fetch_threads
            # Mock should have been called in the thread
            mock.assert_called_once_with("KPAO")

    def test_prefetch_caches_real_metar(self, real_service: WeatherService) -> None:
        """Test that prefetch caches real METAR data."""
        real_weather = Weather(
            icao="KPAO",
            observation_time=datetime.now(UTC),
            wind=Wind(direction=320, speed=8),
            visibility=10.0,
            is_simulated=False,
            raw_metar="KPAO 251756Z 32008KT 10SM CLR 18/08 A3002",
        )

        with patch.object(real_service, "_fetch_metar_sync") as mock:
            mock.return_value = real_weather

            real_service.prefetch_weather("KPAO")
            # Wait for thread to complete
            real_service.wait_for_prefetch("KPAO", timeout=1.0)

            # Should get real weather from cache
            weather = real_service.get_weather_sync("KPAO")
            assert weather.is_simulated is False
            assert weather.raw_metar == "KPAO 251756Z 32008KT 10SM CLR 18/08 A3002"

    def test_prefetch_does_not_duplicate_threads(self, real_service: WeatherService) -> None:
        """Test that multiple prefetch calls don't spawn duplicate threads."""
        with patch.object(real_service, "_fetch_metar_sync") as mock:
            # Make fetch slow to ensure thread is still alive
            import time

            def slow_fetch(icao: str) -> None:
                time.sleep(0.5)
                return None

            mock.side_effect = slow_fetch

            # Call prefetch twice
            real_service.prefetch_weather("KPAO")
            real_service.prefetch_weather("KPAO")  # Should not spawn new thread

            time.sleep(0.1)

            # Should only be one thread
            assert mock.call_count <= 1

    def test_prefetch_disabled_when_use_real_weather_false(self, service: WeatherService) -> None:
        """Test that prefetch does nothing when use_real_weather is False."""
        service.prefetch_weather("KPAO")

        # No thread should be started
        assert "KPAO" not in service._fetch_threads

    def test_wait_for_prefetch_returns_true_when_complete(
        self, real_service: WeatherService
    ) -> None:
        """Test wait_for_prefetch returns True when fetch completes."""
        with patch.object(real_service, "_fetch_metar_sync") as mock:
            mock.return_value = None

            real_service.prefetch_weather("KPAO")
            completed = real_service.wait_for_prefetch("KPAO", timeout=1.0)

            assert completed is True

    def test_wait_for_prefetch_returns_false_when_not_started(
        self, service: WeatherService
    ) -> None:
        """Test wait_for_prefetch returns False when no prefetch was started."""
        result = service.wait_for_prefetch("KPAO", timeout=0.1)
        assert result is False

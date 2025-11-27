"""Tests for weather data models."""

from datetime import UTC, datetime

import pytest

from airborne.services.weather.models import (
    CloudLayer,
    FlightCategory,
    SkyCondition,
    Weather,
    Wind,
)


class TestWind:
    """Tests for Wind dataclass."""

    def test_calm_wind(self) -> None:
        """Test detection of calm winds."""
        wind = Wind(direction=0, speed=0)
        assert wind.is_calm is True
        assert wind.to_atis_string() == "wind calm"

    def test_normal_wind(self) -> None:
        """Test normal wind conditions."""
        wind = Wind(direction=270, speed=15)
        assert wind.is_calm is False
        assert wind.is_variable is False
        assert wind.to_atis_string() == "wind 270 at 15"

    def test_gusting_wind(self) -> None:
        """Test wind with gusts."""
        wind = Wind(direction=180, speed=20, gust=30)
        assert wind.to_atis_string() == "wind 180 at 20 gusting 30"

    def test_variable_direction(self) -> None:
        """Test variable wind direction (-1)."""
        wind = Wind(direction=-1, speed=5)
        assert wind.is_variable is True
        assert wind.to_atis_string() == "wind variable at 5"

    def test_variable_range(self) -> None:
        """Test wind with variable direction range."""
        wind = Wind(direction=270, speed=10, variable_from=240, variable_to=300)
        assert wind.is_variable is True


class TestCloudLayer:
    """Tests for CloudLayer dataclass."""

    def test_basic_layer(self) -> None:
        """Test basic cloud layer."""
        layer = CloudLayer(condition=SkyCondition.SCATTERED, altitude=5000)
        assert layer.to_atis_string() == "SCT 5000"

    def test_layer_with_type(self) -> None:
        """Test cloud layer with cloud type."""
        layer = CloudLayer(condition=SkyCondition.BROKEN, altitude=3000, type="CB")
        assert layer.to_atis_string() == "BKN 3000 CB"


class TestWeather:
    """Tests for Weather dataclass."""

    @pytest.fixture
    def clear_weather(self) -> Weather:
        """Create clear weather fixture."""
        return Weather(
            icao="KPAO",
            observation_time=datetime.now(UTC),
            wind=Wind(direction=270, speed=10),
            visibility=10.0,
            sky=[],
            temperature=20,
            dewpoint=12,
            altimeter=30.05,
        )

    @pytest.fixture
    def ifr_weather(self) -> Weather:
        """Create IFR weather fixture."""
        return Weather(
            icao="KSFO",
            observation_time=datetime.now(UTC),
            wind=Wind(direction=180, speed=15, gust=25),
            visibility=2.0,
            sky=[
                CloudLayer(SkyCondition.BROKEN, 800),
                CloudLayer(SkyCondition.OVERCAST, 1500),
            ],
            temperature=15,
            dewpoint=14,
            altimeter=29.85,
        )

    def test_ceiling_clear(self, clear_weather: Weather) -> None:
        """Test ceiling calculation with clear skies."""
        assert clear_weather.ceiling is None

    def test_ceiling_broken(self, ifr_weather: Weather) -> None:
        """Test ceiling calculation with broken clouds."""
        assert ifr_weather.ceiling == 800

    def test_flight_category_vfr(self, clear_weather: Weather) -> None:
        """Test VFR flight category."""
        assert clear_weather.flight_category == FlightCategory.VFR

    def test_flight_category_ifr(self, ifr_weather: Weather) -> None:
        """Test IFR flight category."""
        assert ifr_weather.flight_category == FlightCategory.IFR

    def test_flight_category_mvfr(self) -> None:
        """Test MVFR flight category."""
        weather = Weather(
            icao="KJFK",
            observation_time=datetime.now(UTC),
            wind=Wind(direction=0, speed=5),
            visibility=4.0,  # Less than 5 SM
            sky=[CloudLayer(SkyCondition.SCATTERED, 4000)],
        )
        assert weather.flight_category == FlightCategory.MVFR

    def test_flight_category_lifr(self) -> None:
        """Test LIFR flight category."""
        weather = Weather(
            icao="KLAX",
            observation_time=datetime.now(UTC),
            wind=Wind(direction=270, speed=3),
            visibility=0.5,  # Less than 1 SM
            sky=[CloudLayer(SkyCondition.OVERCAST, 300)],
        )
        assert weather.flight_category == FlightCategory.LIFR

    def test_sky_condition_clear(self, clear_weather: Weather) -> None:
        """Test sky condition string for clear skies."""
        assert clear_weather.get_sky_condition_string() == "sky clear"

    def test_sky_condition_overcast(self, ifr_weather: Weather) -> None:
        """Test sky condition string for overcast."""
        assert "ceiling" in ifr_weather.get_sky_condition_string()

    def test_to_atis_dict(self, clear_weather: Weather) -> None:
        """Test ATIS dictionary generation."""
        atis = clear_weather.to_atis_dict()
        assert atis["wind_direction"] == 270
        assert atis["wind_speed"] == 10
        assert atis["visibility"] == 10.0
        assert atis["temperature"] == 20
        assert atis["flight_category"] == "VFR"

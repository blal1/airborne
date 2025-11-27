"""Weather simulator for generating realistic weather patterns.

Generates plausible weather when METAR data is unavailable.
"""

import hashlib
import math
import random
from datetime import UTC, datetime

from airborne.core.logging_system import get_logger
from airborne.services.weather.models import CloudLayer, SkyCondition, Weather, Wind

logger = get_logger(__name__)


class WeatherSimulator:
    """Generate simulated weather patterns.

    Uses time-based seeding to ensure consistent weather within 5-minute periods.
    """

    # Weather type distributions (weights for random selection)
    WEATHER_TYPES = {
        "clear": 35,  # Clear skies
        "fair": 25,  # Few/scattered clouds
        "cloudy": 20,  # Broken clouds
        "overcast": 10,  # Overcast
        "marginal": 7,  # Low visibility
        "poor": 3,  # IFR conditions
    }

    def __init__(self, update_interval: float = 300.0):
        """Initialize weather simulator.

        Args:
            update_interval: How often weather changes (default 5 minutes).
        """
        self.update_interval = update_interval

    def generate(self, icao: str, timestamp: datetime | None = None) -> Weather:
        """Generate simulated weather for an airport.

        Args:
            icao: Airport ICAO code.
            timestamp: Time for weather (default: now). Weather is consistent
                      within 5-minute periods.

        Returns:
            Generated Weather object.
        """
        if timestamp is None:
            timestamp = datetime.now(UTC)

        # Create deterministic seed based on ICAO and time period
        time_period = int(timestamp.timestamp() / self.update_interval)
        seed_string = f"{icao}:{time_period}"
        seed = int(hashlib.md5(seed_string.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        # Select weather type
        weather_type = self._select_weather_type(rng)

        # Generate wind
        wind = self._generate_wind(rng, weather_type)

        # Generate sky conditions
        sky = self._generate_sky(rng, weather_type)

        # Generate visibility
        visibility = self._generate_visibility(rng, weather_type)

        # Generate temperature (based on time of day and season)
        temp, dewpoint = self._generate_temperature(rng, timestamp)

        # Generate altimeter
        altimeter = self._generate_altimeter(rng, weather_type)

        return Weather(
            icao=icao,
            observation_time=timestamp,
            wind=wind,
            visibility=visibility,
            sky=sky,
            temperature=temp,
            dewpoint=dewpoint,
            altimeter=altimeter,
            raw_metar=None,
            is_simulated=True,
            remarks="SIMULATED",
        )

    def _select_weather_type(self, rng: random.Random) -> str:
        """Select weather type based on weighted distribution."""
        total = sum(self.WEATHER_TYPES.values())
        roll = rng.randint(1, total)
        cumulative = 0
        for weather_type, weight in self.WEATHER_TYPES.items():
            cumulative += weight
            if roll <= cumulative:
                return weather_type
        return "clear"

    def _generate_wind(self, rng: random.Random, weather_type: str) -> Wind:
        """Generate wind based on weather type."""
        # Wind direction (favoring common directions)
        direction = rng.choice([0, 90, 180, 270]) + rng.randint(-45, 45)
        direction = direction % 360

        # Wind speed based on weather type
        if weather_type in ("clear", "fair"):
            speed = rng.randint(0, 12)
        elif weather_type == "cloudy":
            speed = rng.randint(5, 18)
        elif weather_type == "overcast":
            speed = rng.randint(8, 22)
        else:  # marginal or poor
            speed = rng.randint(10, 28)

        # Gusts (more common in poor weather)
        gust = None
        if speed > 10 and rng.random() < 0.3:  # 30% chance of gusts
            gust = speed + rng.randint(5, 15)

        # Variable winds in light conditions
        if speed < 6 and rng.random() < 0.3:
            direction = -1  # Variable

        return Wind(direction=direction, speed=speed, gust=gust)

    def _generate_sky(self, rng: random.Random, weather_type: str) -> list[CloudLayer]:
        """Generate cloud layers based on weather type."""
        layers = []

        if weather_type == "clear":
            # No clouds
            return []

        if weather_type == "fair":
            # Few or scattered clouds
            if rng.random() < 0.5:
                altitude = rng.randint(4000, 8000)
                layers.append(CloudLayer(SkyCondition.FEW, altitude))
            if rng.random() < 0.3:
                altitude = rng.randint(8000, 12000)
                layers.append(CloudLayer(SkyCondition.SCATTERED, altitude))

        elif weather_type == "cloudy":
            # Broken clouds, possible scattered below
            if rng.random() < 0.5:
                altitude = rng.randint(3000, 5000)
                layers.append(CloudLayer(SkyCondition.SCATTERED, altitude))
            altitude = rng.randint(5000, 10000)
            layers.append(CloudLayer(SkyCondition.BROKEN, altitude))

        elif weather_type == "overcast":
            # Overcast layer
            if rng.random() < 0.4:
                altitude = rng.randint(2000, 4000)
                layers.append(CloudLayer(SkyCondition.BROKEN, altitude))
            altitude = rng.randint(4000, 8000)
            layers.append(CloudLayer(SkyCondition.OVERCAST, altitude))

        elif weather_type == "marginal":
            # Low broken/overcast
            altitude = rng.randint(1500, 3000)
            condition = rng.choice([SkyCondition.BROKEN, SkyCondition.OVERCAST])
            layers.append(CloudLayer(condition, altitude))

        else:  # poor
            # Very low ceiling
            altitude = rng.randint(500, 1500)
            layers.append(CloudLayer(SkyCondition.OVERCAST, altitude))

        return sorted(layers, key=lambda x: x.altitude)

    def _generate_visibility(self, rng: random.Random, weather_type: str) -> float:
        """Generate visibility based on weather type."""
        if weather_type in ("clear", "fair"):
            return rng.choice([10.0, 10.0, 10.0, 8.0, 9.0])  # Usually 10 SM
        if weather_type == "cloudy":
            return rng.choice([6.0, 7.0, 8.0, 10.0])
        if weather_type == "overcast":
            return rng.choice([5.0, 6.0, 7.0, 8.0])
        if weather_type == "marginal":
            return rng.choice([3.0, 4.0, 5.0, 6.0])
        # poor
        return rng.choice([1.0, 1.5, 2.0, 2.5])

    def _generate_temperature(self, rng: random.Random, timestamp: datetime) -> tuple[int, int]:
        """Generate temperature and dewpoint based on time of day."""
        hour = timestamp.hour

        # Base temperature varies by time of day
        if 6 <= hour < 10:  # Morning
            base_temp = rng.randint(10, 18)
        elif 10 <= hour < 16:  # Afternoon
            base_temp = rng.randint(18, 28)
        elif 16 <= hour < 20:  # Evening
            base_temp = rng.randint(15, 24)
        else:  # Night
            base_temp = rng.randint(8, 16)

        # Dewpoint is typically lower than temperature
        spread = rng.randint(4, 12)
        dewpoint = base_temp - spread

        return base_temp, dewpoint

    def _generate_altimeter(self, rng: random.Random, weather_type: str) -> float:
        """Generate altimeter setting based on weather type."""
        # Normal range: 29.70 - 30.30
        if weather_type in ("clear", "fair"):
            # Higher pressure in good weather
            return round(29.90 + rng.random() * 0.30, 2)
        if weather_type in ("cloudy", "overcast"):
            # Normal pressure
            return round(29.80 + rng.random() * 0.30, 2)
        # Low pressure in poor weather
        return round(29.60 + rng.random() * 0.30, 2)


def calculate_active_runway(
    runways: list[tuple[str, int]], wind_direction: int, wind_speed: int
) -> str:
    """Calculate the best runway based on wind.

    Args:
        runways: List of (runway_id, heading) tuples.
        wind_direction: Wind direction in degrees.
        wind_speed: Wind speed in knots.

    Returns:
        Best runway ID for landing/takeoff.
    """
    if wind_speed < 5:
        # Light wind - any runway is fine, return first
        return runways[0][0] if runways else "36"

    best_runway = runways[0][0] if runways else "36"
    best_headwind: float = -999.0

    for runway_id, heading in runways:
        # Calculate headwind component
        wind_angle = math.radians(wind_direction - heading)
        headwind = wind_speed * math.cos(wind_angle)

        if headwind > best_headwind:
            best_headwind = headwind
            best_runway = runway_id

    return best_runway

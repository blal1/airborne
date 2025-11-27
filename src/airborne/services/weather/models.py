"""Weather data models for aviation weather services.

Provides structured weather data following aviation standards.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SkyCondition(Enum):
    """Sky condition categories per aviation standards."""

    CLEAR = "CLR"  # Clear below 12,000 ft
    FEW = "FEW"  # 1/8 to 2/8 coverage
    SCATTERED = "SCT"  # 3/8 to 4/8 coverage
    BROKEN = "BKN"  # 5/8 to 7/8 coverage (ceiling)
    OVERCAST = "OVC"  # 8/8 coverage (ceiling)
    VERTICAL_VISIBILITY = "VV"  # Obscured sky


class FlightCategory(Enum):
    """Flight category based on ceiling and visibility."""

    VFR = "VFR"  # Ceiling >3000 ft AND visibility >5 SM
    MVFR = "MVFR"  # Ceiling 1000-3000 ft OR visibility 3-5 SM
    IFR = "IFR"  # Ceiling 500-1000 ft OR visibility 1-3 SM
    LIFR = "LIFR"  # Ceiling <500 ft OR visibility <1 SM


@dataclass
class Wind:
    """Wind information.

    Attributes:
        direction: Wind direction in degrees (0-360), or -1 for variable.
        speed: Wind speed in knots.
        gust: Gust speed in knots, or None if no gusts.
        variable_from: Variable wind direction start, or None.
        variable_to: Variable wind direction end, or None.
    """

    direction: int
    speed: int
    gust: int | None = None
    variable_from: int | None = None
    variable_to: int | None = None

    @property
    def is_calm(self) -> bool:
        """Check if wind is calm (0 knots)."""
        return self.speed == 0

    @property
    def is_variable(self) -> bool:
        """Check if wind direction is variable."""
        return self.direction == -1 or self.variable_from is not None

    def to_atis_string(self) -> str:
        """Convert to ATIS-style wind string."""
        if self.is_calm:
            return "wind calm"
        direction_str = "variable" if self.direction == -1 else f"{self.direction:03d}"
        result = f"wind {direction_str} at {self.speed}"
        if self.gust:
            result += f" gusting {self.gust}"
        return result


@dataclass
class CloudLayer:
    """Single cloud layer.

    Attributes:
        condition: Sky condition (FEW, SCT, BKN, OVC).
        altitude: Cloud base altitude in feet AGL.
        type: Cloud type (e.g., "CB" for cumulonimbus), or None.
    """

    condition: SkyCondition
    altitude: int
    type: str | None = None

    def to_atis_string(self) -> str:
        """Convert to ATIS-style cloud string."""
        result = f"{self.condition.value} {self.altitude}"
        if self.type:
            result += f" {self.type}"
        return result


@dataclass
class Weather:
    """Complete weather observation.

    Attributes:
        icao: Airport ICAO code.
        observation_time: Time of observation (UTC).
        wind: Wind information.
        visibility: Visibility in statute miles.
        sky: List of cloud layers (lowest first).
        temperature: Temperature in Celsius.
        dewpoint: Dewpoint in Celsius.
        altimeter: Altimeter setting (inches Hg for US, hPa for Europe).
        pressure_unit: Pressure unit ("inHg" or "hPa").
        raw_metar: Original METAR string, if from real data.
        is_simulated: True if weather is simulated, not from METAR.
        remarks: Additional remarks from METAR.
    """

    icao: str
    observation_time: datetime
    wind: Wind
    visibility: float
    sky: list[CloudLayer] = field(default_factory=list)
    temperature: int = 15
    dewpoint: int = 10
    altimeter: float = 29.92
    pressure_unit: str = "inHg"  # "inHg" for US, "hPa" for Europe/ICAO
    raw_metar: str | None = None
    is_simulated: bool = False
    remarks: str = ""

    @property
    def ceiling(self) -> int | None:
        """Get ceiling altitude (lowest BKN or OVC layer)."""
        for layer in self.sky:
            if layer.condition in (SkyCondition.BROKEN, SkyCondition.OVERCAST):
                return layer.altitude
        return None

    @property
    def flight_category(self) -> FlightCategory:
        """Determine flight category based on ceiling and visibility."""
        ceiling = self.ceiling

        # Check LIFR
        if (ceiling is not None and ceiling < 500) or self.visibility < 1:
            return FlightCategory.LIFR

        # Check IFR
        if (ceiling is not None and ceiling < 1000) or self.visibility < 3:
            return FlightCategory.IFR

        # Check MVFR
        if (ceiling is not None and ceiling < 3000) or self.visibility < 5:
            return FlightCategory.MVFR

        return FlightCategory.VFR

    def get_sky_condition_string(self) -> str:
        """Get human-readable sky condition."""
        if not self.sky:
            return "sky clear"

        # Find the most significant layer
        for layer in self.sky:
            if layer.condition == SkyCondition.OVERCAST:
                return f"overcast at {layer.altitude} feet"
            if layer.condition == SkyCondition.BROKEN:
                return f"ceiling {layer.altitude} feet broken"

        # No ceiling, describe first layer
        if self.sky:
            layer = self.sky[0]
            if layer.condition == SkyCondition.FEW:
                return f"few clouds at {layer.altitude} feet"
            if layer.condition == SkyCondition.SCATTERED:
                return f"scattered clouds at {layer.altitude} feet"

        return "sky clear"

    def to_atis_dict(self) -> dict:
        """Convert to dictionary for ATIS generation."""
        return {
            "wind_direction": self.wind.direction,
            "wind_speed": self.wind.speed,
            "wind_gust": self.wind.gust,
            "visibility": self.visibility,
            "sky_condition": self.get_sky_condition_string(),
            "ceiling": self.ceiling,
            "temperature": self.temperature,
            "dewpoint": self.dewpoint,
            "altimeter": self.altimeter,
            "flight_category": self.flight_category.value,
        }

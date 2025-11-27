"""METAR string parser for aviation weather data.

Parses raw METAR strings into structured Weather objects.
"""

import re
from datetime import UTC, datetime

from airborne.core.logging_system import get_logger
from airborne.services.weather.models import CloudLayer, SkyCondition, Weather, Wind

logger = get_logger(__name__)


class METARParser:
    """Parse METAR strings into Weather objects.

    Handles standard METAR format as used in US aviation.
    """

    # Regex patterns for METAR components
    WIND_PATTERN = re.compile(
        r"(\d{3}|VRB)(\d{2,3})(G(\d{2,3}))?KT"
        r"(?:\s+(\d{3})V(\d{3}))?"  # Variable wind direction
    )
    # Visibility pattern: must be preceded by space and handle SM format
    # Match "10SM" or "1/2SM" or "3SM" etc. - NOT 4-digit meter format to avoid matching time
    VISIBILITY_PATTERN = re.compile(r"\s(\d+)(?:/(\d+))?SM")
    SKY_PATTERN = re.compile(r"(CLR|SKC|FEW|SCT|BKN|OVC|VV)(\d{3})?(CB|TCU)?")
    TEMP_PATTERN = re.compile(r"(M)?(\d{2})/(M)?(\d{2})")
    ALTIMETER_PATTERN = re.compile(r"A(\d{4})")  # US: A2992 = 29.92 inHg
    QNH_PATTERN = re.compile(r"Q(\d{4})")  # ICAO/Europe: Q1013 = 1013 hPa
    TIME_PATTERN = re.compile(r"(\d{2})(\d{2})(\d{2})Z")

    def parse(self, raw_metar: str) -> Weather | None:
        """Parse a raw METAR string into a Weather object.

        Args:
            raw_metar: Raw METAR string (e.g., "KPAO 251756Z 32008KT 10SM CLR 18/08 A3002")

        Returns:
            Weather object, or None if parsing fails.
        """
        if not raw_metar or len(raw_metar) < 10:
            logger.warning("METAR too short to parse: %s", raw_metar)
            return None

        try:
            parts = raw_metar.upper().split()
            if len(parts) < 5:
                logger.warning("METAR has too few parts: %s", raw_metar)
                return None

            # Skip "METAR" or "SPECI" prefix if present
            start_idx = 0
            if parts[0] in ("METAR", "SPECI"):
                start_idx = 1

            # First part after prefix is ICAO code
            icao = parts[start_idx]
            if len(icao) != 4:
                logger.warning("Invalid ICAO code: %s", icao)
                return None

            # Parse observation time (next part after ICAO)
            obs_time = self._parse_time(parts[start_idx + 1])

            # Parse wind
            wind = self._parse_wind(raw_metar)
            if wind is None:
                wind = Wind(direction=0, speed=0)  # Default calm

            # Parse visibility
            visibility = self._parse_visibility(raw_metar)

            # Parse sky conditions
            sky_layers = self._parse_sky(raw_metar)

            # Parse temperature/dewpoint
            temp, dewpoint = self._parse_temperature(raw_metar)

            # Parse altimeter/QNH
            altimeter, pressure_unit = self._parse_pressure(raw_metar)

            # Build remarks (everything after RMK)
            remarks = ""
            if "RMK" in raw_metar:
                remarks = raw_metar.split("RMK")[1].strip()

            return Weather(
                icao=icao,
                observation_time=obs_time,
                wind=wind,
                visibility=visibility,
                sky=sky_layers,
                temperature=temp,
                dewpoint=dewpoint,
                altimeter=altimeter,
                pressure_unit=pressure_unit,
                raw_metar=raw_metar,
                is_simulated=False,
                remarks=remarks,
            )

        except Exception as e:
            logger.error("Failed to parse METAR '%s': %s", raw_metar, e)
            return None

    def _parse_time(self, time_str: str) -> datetime:
        """Parse METAR time string (DDHHMM)Z."""
        match = self.TIME_PATTERN.match(time_str)
        if match:
            day = int(match.group(1))
            hour = int(match.group(2))
            minute = int(match.group(3))
            now = datetime.now(UTC)
            return now.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
        return datetime.now(UTC)

    def _parse_wind(self, metar: str) -> Wind | None:
        """Parse wind information from METAR."""
        match = self.WIND_PATTERN.search(metar)
        if not match:
            # Check for calm wind
            if "00000KT" in metar:
                return Wind(direction=0, speed=0)
            return None

        direction_str = match.group(1)
        direction = -1 if direction_str == "VRB" else int(direction_str)

        speed = int(match.group(2))
        gust = int(match.group(4)) if match.group(4) else None

        # Variable wind direction range
        var_from = int(match.group(5)) if match.group(5) else None
        var_to = int(match.group(6)) if match.group(6) else None

        return Wind(
            direction=direction,
            speed=speed,
            gust=gust,
            variable_from=var_from,
            variable_to=var_to,
        )

    def _parse_visibility(self, metar: str) -> float:
        """Parse visibility from METAR (returns statute miles)."""
        match = self.VISIBILITY_PATTERN.search(metar)
        if not match:
            return 10.0  # Default to 10 SM

        # SM format - group 1 is whole number, group 2 is denominator for fractions
        whole = int(match.group(1))
        if match.group(2):
            # Fractional (e.g., 1/2SM means visibility = 1/2 = 0.5 SM)
            fraction = int(match.group(2))
            return whole / fraction
        return float(whole)

    def _parse_sky(self, metar: str) -> list[CloudLayer]:
        """Parse sky conditions from METAR."""
        layers = []
        for match in self.SKY_PATTERN.finditer(metar):
            condition_str = match.group(1)
            altitude_str = match.group(2)
            cloud_type = match.group(3)  # CB or TCU

            # Map condition string to enum
            condition_map = {
                "CLR": SkyCondition.CLEAR,
                "SKC": SkyCondition.CLEAR,
                "FEW": SkyCondition.FEW,
                "SCT": SkyCondition.SCATTERED,
                "BKN": SkyCondition.BROKEN,
                "OVC": SkyCondition.OVERCAST,
                "VV": SkyCondition.VERTICAL_VISIBILITY,
            }
            condition = condition_map.get(condition_str, SkyCondition.CLEAR)

            # Skip clear sky entries (no altitude)
            if condition == SkyCondition.CLEAR and not altitude_str:
                continue

            altitude = int(altitude_str) * 100 if altitude_str else 0

            layers.append(CloudLayer(condition=condition, altitude=altitude, type=cloud_type))

        return layers

    def _parse_temperature(self, metar: str) -> tuple[int, int]:
        """Parse temperature and dewpoint from METAR."""
        match = self.TEMP_PATTERN.search(metar)
        if not match:
            return 15, 10  # Default values

        temp = int(match.group(2))
        if match.group(1):  # M prefix = minus
            temp = -temp

        dewpoint = int(match.group(4))
        if match.group(3):  # M prefix = minus
            dewpoint = -dewpoint

        return temp, dewpoint

    def _parse_pressure(self, metar: str) -> tuple[float, str]:
        """Parse altimeter/QNH setting from METAR.

        Returns:
            Tuple of (pressure value, unit). Unit is "inHg" or "hPa".
        """
        # Try US altimeter first (A prefix)
        match = self.ALTIMETER_PATTERN.search(metar)
        if match:
            # A3002 = 30.02 inches Hg
            value = int(match.group(1))
            return value / 100.0, "inHg"

        # Try ICAO/European QNH (Q prefix)
        match = self.QNH_PATTERN.search(metar)
        if match:
            # Q1013 = 1013 hPa
            value = int(match.group(1))
            return float(value), "hPa"

        # Default to standard pressure in inHg
        return 29.92, "inHg"

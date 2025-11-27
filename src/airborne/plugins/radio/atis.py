"""Automatic Terminal Information Service (ATIS) system."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from airborne.services.weather.models import Weather


# =============================================================================
# Aviation Phraseology Helpers (English)
# =============================================================================
# NOTE: These functions are language-specific (English aviation phraseology).
# For multi-language support, consider:
# 1. Moving to a separate phraseology module per language
# 2. Using a Phraseology class with language-specific subclasses
# 3. Loading phraseology from configuration files
# =============================================================================

# Digit to spoken word mapping (aviation standard)
_DIGIT_WORDS = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "niner",  # Aviation standard uses "niner" to avoid confusion with "five"
}


def _digits_to_words(value: str) -> str:
    """Convert a string of digits to spoken words.

    Args:
        value: String containing digits (e.g., "310", "1455").

    Returns:
        Space-separated spoken words (e.g., "three one zero").

    Examples:
        >>> _digits_to_words("310")
        'three one zero'
        >>> _digits_to_words("1455")
        'one four five five'
    """
    return " ".join(_DIGIT_WORDS.get(d, d) for d in value)


def _format_time_spoken(time_str: str) -> str:
    """Format time (HHMM) for spoken ATIS.

    Args:
        time_str: Time in HHMM format (e.g., "1455").

    Returns:
        Spoken time (e.g., "one four five five").

    Examples:
        >>> _format_time_spoken("1455")
        'one four five five'
        >>> _format_time_spoken("0830")
        'zero eight three zero'
    """
    return _digits_to_words(time_str)


def _format_wind_direction_spoken(direction: int) -> str:
    """Format wind direction for spoken ATIS.

    Args:
        direction: Wind direction in degrees (0-360).

    Returns:
        Spoken direction (e.g., "three one zero").

    Examples:
        >>> _format_wind_direction_spoken(310)
        'three one zero'
        >>> _format_wind_direction_spoken(90)
        'zero niner zero'
    """
    return _digits_to_words(f"{direction:03d}")


def _format_altimeter_spoken(altimeter: float) -> str:
    """Format altimeter setting for spoken ATIS (US format).

    Args:
        altimeter: Altimeter in inches Hg (e.g., 30.12).

    Returns:
        Spoken altimeter (e.g., "three zero one two").

    Examples:
        >>> _format_altimeter_spoken(30.12)
        'three zero one two'
        >>> _format_altimeter_spoken(29.92)
        'two niner niner two'
    """
    # Remove decimal point and format as 4 digits
    alt_str = f"{altimeter:.2f}".replace(".", "")
    return _digits_to_words(alt_str)


def _format_qnh_spoken(qnh: int) -> str:
    """Format QNH for spoken ATIS (European format).

    Args:
        qnh: QNH in hectopascals (e.g., 1013).

    Returns:
        Spoken QNH (e.g., "one zero one three").

    Examples:
        >>> _format_qnh_spoken(1013)
        'one zero one three'
        >>> _format_qnh_spoken(998)
        'niner niner eight'
    """
    return _digits_to_words(str(qnh))


def _format_runway_spoken(runway: str) -> str:
    """Format runway identifier for spoken ATIS.

    Args:
        runway: Runway identifier (e.g., "31", "31L", "07R").

    Returns:
        Spoken runway (e.g., "three one", "three one left").

    Examples:
        >>> _format_runway_spoken("31")
        'three one'
        >>> _format_runway_spoken("31L")
        'three one left'
        >>> _format_runway_spoken("07R")
        'zero seven right'
    """
    # Mapping for runway suffix letters
    suffix_map = {"L": "left", "R": "right", "C": "center"}

    # Extract numbers and suffix
    numbers = "".join(c for c in runway if c.isdigit())
    suffix = "".join(c for c in runway if c.isalpha())

    result = _digits_to_words(numbers)
    if suffix and suffix.upper() in suffix_map:
        result += f" {suffix_map[suffix.upper()]}"

    return result


def _format_visibility_spoken(visibility: float) -> str:
    """Format visibility for spoken ATIS.

    Args:
        visibility: Visibility in statute miles.

    Returns:
        Spoken visibility phrase.

    Examples:
        >>> _format_visibility_spoken(10)
        'one zero'
        >>> _format_visibility_spoken(3)
        'three'
        >>> _format_visibility_spoken(0.5)
        'one half'
    """
    if visibility >= 10:
        return "one zero"
    if visibility >= 1:
        return _digits_to_words(str(int(visibility)))

    # Common fractions for low visibility
    fraction_map = {
        0.25: "one quarter",
        0.5: "one half",
        0.75: "three quarters",
    }
    return fraction_map.get(visibility, f"{visibility:.1f}")


@dataclass
class WeatherInfo:
    """Weather information for ATIS broadcast.

    Attributes:
        wind_direction: Wind direction in degrees (magnetic)
        wind_speed: Wind speed in knots
        wind_gusts: Gust speed in knots (None if no gusts)
        visibility: Visibility in statute miles
        sky_condition: Sky condition (e.g., "clear", "few clouds", "overcast")
        temperature_c: Temperature in Celsius
        dewpoint_c: Dewpoint in Celsius
        altimeter: Altimeter setting in inches Hg
    """

    wind_direction: int
    wind_speed: int
    wind_gusts: int | None = None
    visibility: int = 10
    sky_condition: str = "clear"
    temperature_c: int = 20
    dewpoint_c: int = 15
    altimeter: float = 29.92


@dataclass
class ATISInfo:
    """Complete ATIS information.

    Attributes:
        airport_name: Full airport name
        information_letter: ATIS information letter (A-Z)
        time_zulu: Time in Zulu (UTC) format (HHMM)
        weather: Weather information
        active_runway: Active runway for arrivals/departures
        remarks: Additional remarks (optional)
        include_parking_instructions: Whether to include parking assignment instructions
    """

    airport_name: str
    information_letter: str
    time_zulu: str
    weather: WeatherInfo
    active_runway: str
    remarks: str = ""
    include_parking_instructions: bool = True


class ATISGenerator:
    """Generates ATIS broadcasts with realistic phraseology.

    Follows standard ATIS format:
    1. Airport name and information letter
    2. Time (Zulu)
    3. Wind
    4. Visibility
    5. Sky condition
    6. Temperature/dewpoint
    7. Altimeter
    8. Active runway(s)
    9. Remarks
    10. Advise on initial contact

    Examples:
        >>> weather = WeatherInfo(
        ...     wind_direction=310,
        ...     wind_speed=8,
        ...     visibility=10,
        ...     sky_condition="clear",
        ...     temperature_c=22,
        ...     dewpoint_c=14,
        ...     altimeter=30.12
        ... )
        >>> atis_info = ATISInfo(
        ...     airport_name="Palo Alto Airport",
        ...     information_letter="Bravo",
        ...     time_zulu="1455",
        ...     weather=weather,
        ...     active_runway="31"
        ... )
        >>> generator = ATISGenerator()
        >>> broadcast = generator.generate(atis_info)
    """

    # Phonetic alphabet for information letters
    PHONETIC_ALPHABET = [
        "Alpha",
        "Bravo",
        "Charlie",
        "Delta",
        "Echo",
        "Foxtrot",
        "Golf",
        "Hotel",
        "India",
        "Juliet",
        "Kilo",
        "Lima",
        "Mike",
        "November",
        "Oscar",
        "Papa",
        "Quebec",
        "Romeo",
        "Sierra",
        "Tango",
        "Uniform",
        "Victor",
        "Whiskey",
        "X-ray",
        "Yankee",
        "Zulu",
    ]

    def __init__(self) -> None:
        """Initialize ATIS generator."""
        self._current_letter_index = 0

    def generate(self, atis_info: ATISInfo) -> str:
        """Generate ATIS broadcast text.

        Args:
            atis_info: Complete ATIS information

        Returns:
            Formatted ATIS broadcast text

        Examples:
            >>> weather = WeatherInfo(310, 8, None, 10, "clear", 22, 14, 30.12)
            >>> info = ATISInfo("Palo Alto Airport", "Bravo", "1455", weather, "31")
            >>> generator = ATISGenerator()
            >>> broadcast = generator.generate(info)
            >>> "Palo Alto Airport" in broadcast
            True
        """
        parts = []

        # 1. Introduction
        parts.append(f"{atis_info.airport_name} information {atis_info.information_letter}.")

        # 2. Time
        parts.append(f"Time {atis_info.time_zulu} Zulu.")

        # 3. Wind
        wind_text = self._format_wind(atis_info.weather)
        parts.append(wind_text)

        # 4. Visibility
        parts.append(f"Visibility {atis_info.weather.visibility} statute miles.")

        # 5. Sky condition
        parts.append(f"Sky {atis_info.weather.sky_condition}.")

        # 6. Temperature and dewpoint
        temp_text = self._format_temperature(atis_info.weather)
        parts.append(temp_text)

        # 7. Altimeter
        altimeter_text = self._format_altimeter(atis_info.weather.altimeter)
        parts.append(altimeter_text)

        # 8. Active runway
        parts.append(f"Landing and departing runway {atis_info.active_runway}.")

        # 9. Remarks (if any)
        if atis_info.remarks:
            parts.append(f"Remarks. {atis_info.remarks}.")

        # 10. Parking/ground instructions for arrivals
        if atis_info.include_parking_instructions:
            parts.append("Inbound aircraft contact ground on 121.7 for parking assignment.")

        # 11. Advise on contact
        parts.append(
            f"Advise on initial contact you have information {atis_info.information_letter}."
        )

        return " ".join(parts)

    def _format_wind(self, weather: WeatherInfo) -> str:
        """Format wind information.

        Args:
            weather: Weather information

        Returns:
            Formatted wind text
        """
        if weather.wind_speed == 0:
            return "Wind calm."

        wind_text = f"Wind {weather.wind_direction:03d} at {weather.wind_speed}"

        if weather.wind_gusts:
            wind_text += f", gusts {weather.wind_gusts}"

        wind_text += " knots."
        return wind_text

    def _format_temperature(self, weather: WeatherInfo) -> str:
        """Format temperature and dewpoint.

        Args:
            weather: Weather information

        Returns:
            Formatted temperature text
        """
        return f"Temperature {weather.temperature_c}, dewpoint {weather.dewpoint_c}."

    def _format_altimeter(self, altimeter: float) -> str:
        """Format altimeter setting.

        Args:
            altimeter: Altimeter in inches Hg

        Returns:
            Formatted altimeter text
        """
        return f"Altimeter {altimeter:.2f}."

    def get_next_information_letter(self) -> str:
        """Get the next information letter in sequence.

        Returns:
            Next phonetic letter (Alpha, Bravo, etc.)

        Examples:
            >>> generator = ATISGenerator()
            >>> generator.get_next_information_letter()
            'Alpha'
            >>> generator.get_next_information_letter()
            'Bravo'
        """
        letter = self.PHONETIC_ALPHABET[self._current_letter_index]
        self._current_letter_index = (self._current_letter_index + 1) % len(self.PHONETIC_ALPHABET)
        return letter

    def create_default_atis(
        self,
        airport_name: str,
        active_runway: str,
        wind_direction: int | None = None,
        wind_speed: int | None = None,
    ) -> ATISInfo:
        """Create ATIS with default/current conditions.

        Args:
            airport_name: Name of the airport
            active_runway: Active runway identifier
            wind_direction: Optional wind direction (defaults to runway heading)
            wind_speed: Optional wind speed (defaults to 5 knots)

        Returns:
            ATISInfo with default conditions

        Examples:
            >>> generator = ATISGenerator()
            >>> atis = generator.create_default_atis("Palo Alto Airport", "31")
            >>> atis.airport_name
            'Palo Alto Airport'
        """
        # Default wind from runway direction if not specified
        if wind_direction is None:
            wind_direction = int(active_runway.lstrip("0")) * 10

        if wind_speed is None:
            wind_speed = 5

        # Get current time
        now = datetime.utcnow()
        time_zulu = now.strftime("%H%M")

        # Create default weather
        weather = WeatherInfo(
            wind_direction=wind_direction,
            wind_speed=wind_speed,
            wind_gusts=None,
            visibility=10,
            sky_condition="clear",
            temperature_c=20,
            dewpoint_c=15,
            altimeter=29.92,
        )

        # Get next information letter
        info_letter = self.get_next_information_letter()

        return ATISInfo(
            airport_name=airport_name,
            information_letter=info_letter,
            time_zulu=time_zulu,
            weather=weather,
            active_runway=active_runway,
            remarks="",
        )

    def update_atis(
        self,
        current_atis: ATISInfo,
        wind_changed: bool = False,
        runway_changed: bool = False,
        weather_changed: bool = False,
    ) -> ATISInfo:
        """Update ATIS and increment information letter if conditions changed.

        Args:
            current_atis: Current ATIS information
            wind_changed: Whether wind has changed significantly
            runway_changed: Whether active runway changed
            weather_changed: Whether weather changed significantly

        Returns:
            Updated ATISInfo with new letter if conditions changed

        Examples:
            >>> generator = ATISGenerator()
            >>> old_atis = generator.create_default_atis("Palo Alto Airport", "31")
            >>> new_atis = generator.update_atis(old_atis, runway_changed=True)
            >>> old_atis.information_letter != new_atis.information_letter
            True
        """
        # If conditions changed, get new letter
        if wind_changed or runway_changed or weather_changed:
            new_letter = self.get_next_information_letter()
            current_atis.information_letter = new_letter

            # Update time
            now = datetime.utcnow()
            current_atis.time_zulu = now.strftime("%H%M")

        return current_atis

    def generate_from_weather(
        self,
        airport_name: str,
        airport_icao: str,
        active_runway: str,
        weather: "Weather",
    ) -> str:
        """Generate ATIS text directly from Weather model.

        Creates a realistic ATIS broadcast with proper aviation phraseology.
        Numbers are spoken digit-by-digit per aviation standards.
        Handles both US (inHg) and European (hPa/QNH) pressure formats.

        Args:
            airport_name: Full airport name (e.g., "Palo Alto Airport").
            airport_icao: Airport ICAO code (e.g., "KPAO").
            active_runway: Active runway identifier (e.g., "31").
            weather: Weather object from WeatherService.

        Returns:
            Complete ATIS broadcast text with proper phraseology for TTS.
        """
        # Get information letter
        info_letter = self.get_next_information_letter()

        # Format time from weather observation (spoken digit-by-digit)
        time_zulu = weather.observation_time.strftime("%H%M")
        time_spoken = _format_time_spoken(time_zulu)

        parts = []

        # 1. Introduction
        parts.append(f"{airport_name} information {info_letter}.")

        # 2. Time (Zulu) - spoken digit-by-digit
        parts.append(f"Time {time_spoken} zulu.")

        # 3. Wind - direction spoken digit-by-digit
        wind = weather.wind
        if wind.is_calm:
            parts.append("Wind calm.")
        elif wind.is_variable and wind.direction == -1:
            wind_text = f"Wind variable at {wind.speed}"
            if wind.gust:
                wind_text += f", gusts {wind.gust}"
            wind_text += "."
            parts.append(wind_text)
        else:
            wind_dir_spoken = _format_wind_direction_spoken(wind.direction)
            wind_text = f"Wind {wind_dir_spoken} at {wind.speed}"
            if wind.gust:
                wind_text += f", gusts {wind.gust}"
            wind_text += "."
            parts.append(wind_text)

        # 4. Visibility - spoken with proper phraseology
        vis_spoken = _format_visibility_spoken(weather.visibility)
        if weather.visibility >= 10:
            parts.append(f"Visibility {vis_spoken} miles or better.")
        else:
            parts.append(f"Visibility {vis_spoken} miles.")

        # 5. Sky condition
        sky_desc = weather.get_sky_condition_string()
        parts.append(f"Sky condition {sky_desc}.")

        # 6. Temperature and dewpoint
        temp = weather.temperature
        dew = weather.dewpoint
        # Handle negative temperatures
        temp_str = f"minus {abs(temp)}" if temp < 0 else str(temp)
        dew_str = f"minus {abs(dew)}" if dew < 0 else str(dew)
        parts.append(f"Temperature {temp_str}, dewpoint {dew_str}.")

        # 7. Altimeter/QNH - spoken digit-by-digit, handle EU vs US formats
        if weather.pressure_unit == "hPa":
            # European format: QNH in hectopascals
            qnh_spoken = _format_qnh_spoken(int(weather.altimeter))
            parts.append(f"QNH {qnh_spoken}.")
        else:
            # US format: Altimeter in inches Hg
            alt_spoken = _format_altimeter_spoken(weather.altimeter)
            parts.append(f"Altimeter {alt_spoken}.")

        # 8. Active runway - spoken digit-by-digit
        runway_spoken = _format_runway_spoken(active_runway)
        parts.append(f"Landing and departing runway {runway_spoken}.")

        # 9. Remarks (if any)
        if weather.remarks:
            # Truncate long remarks
            remarks = weather.remarks[:100]
            parts.append(f"Remarks, {remarks}.")

        # 10. METAR source indicator
        if weather.is_simulated:
            parts.append("Note, simulated weather data.")

        # 11. Advise on initial contact
        parts.append(f"Advise on initial contact you have information {info_letter}.")

        # Join with spaces - periods provide natural pauses for TTS
        return " ".join(parts)

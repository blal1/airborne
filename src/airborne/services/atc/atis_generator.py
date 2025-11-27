"""Dynamic ATIS generator with concatenated audio support.

Generates realistic ATIS broadcasts using weather data and
produces audio by concatenating pre-recorded word files.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from airborne.core.logging_system import get_logger
from airborne.services.atc.phraseology import PhoneticConverter, PhraseBuilder
from airborne.services.weather import Weather, WeatherService, calculate_active_runway

logger = get_logger(__name__)


# ATIS information letters cycle A-Z
INFORMATION_LETTERS = [
    "alpha",
    "bravo",
    "charlie",
    "delta",
    "echo",
    "foxtrot",
    "golf",
    "hotel",
    "india",
    "juliett",
    "kilo",
    "lima",
    "mike",
    "november",
    "oscar",
    "papa",
    "quebec",
    "romeo",
    "sierra",
    "tango",
    "uniform",
    "victor",
    "whiskey",
    "x-ray",
    "yankee",
    "zulu",
]


@dataclass
class ATISBroadcast:
    """Complete ATIS broadcast data.

    Attributes:
        airport_icao: Airport ICAO code.
        airport_name: Full airport name.
        information_letter: Current ATIS information letter.
        observation_time: Time of weather observation.
        weather: Weather data for the broadcast.
        active_runway: Active runway for arrivals/departures.
        remarks: Additional remarks.
        text: Full text of the ATIS broadcast.
        words: List of individual words for audio concatenation.
    """

    airport_icao: str
    airport_name: str
    information_letter: str
    observation_time: datetime
    weather: Weather
    active_runway: str
    remarks: str = ""
    text: str = ""
    words: list[str] = field(default_factory=list)


class DynamicATISGenerator:
    """Generate dynamic ATIS broadcasts from weather data.

    Creates ATIS broadcasts that update based on current weather,
    with proper aviation phraseology.
    """

    def __init__(
        self,
        weather_service: WeatherService | None = None,
        audio_base_path: str = "data/speech/en",
    ) -> None:
        """Initialize ATIS generator.

        Args:
            weather_service: Weather service for getting current weather.
            audio_base_path: Base path for audio files.
        """
        self._weather_service = weather_service or WeatherService()
        self._phrase_builder = PhraseBuilder(audio_base_path)
        self._current_letter_index = 0
        self._last_weather: dict[str, Weather] = {}
        self._airport_info: dict[str, dict[str, Any]] = {}

    def register_airport(
        self,
        icao: str,
        name: str,
        runways: list[tuple[str, int]],
        tower_freq: float = 118.5,
        ground_freq: float = 121.7,
        atis_freq: float = 127.0,
    ) -> None:
        """Register an airport for ATIS generation.

        Args:
            icao: Airport ICAO code.
            name: Full airport name.
            runways: List of (runway_id, heading) tuples.
            tower_freq: Tower frequency.
            ground_freq: Ground frequency.
            atis_freq: ATIS frequency.
        """
        self._airport_info[icao.upper()] = {
            "name": name,
            "runways": runways,
            "tower_freq": tower_freq,
            "ground_freq": ground_freq,
            "atis_freq": atis_freq,
        }

    def generate(
        self,
        icao: str,
        weather: Weather | None = None,
        force_new_letter: bool = False,
    ) -> ATISBroadcast:
        """Generate an ATIS broadcast for an airport.

        Args:
            icao: Airport ICAO code.
            weather: Optional weather data (fetched if not provided).
            force_new_letter: Force new information letter.

        Returns:
            Complete ATIS broadcast.
        """
        icao = icao.upper()

        # Get airport info
        airport_info = self._airport_info.get(
            icao,
            {
                "name": f"{icao} Airport",
                "runways": [("36", 360), ("18", 180)],
                "tower_freq": 118.5,
                "ground_freq": 121.7,
                "atis_freq": 127.0,
            },
        )

        # Get weather
        if weather is None:
            weather = self._weather_service.get_weather_sync(icao)

        # Check if weather changed significantly
        last_weather = self._last_weather.get(icao)
        weather_changed = self._weather_changed(last_weather, weather)

        if weather_changed or force_new_letter:
            self._advance_letter()

        self._last_weather[icao] = weather

        # Determine active runway
        active_runway = calculate_active_runway(
            airport_info["runways"],
            weather.wind.direction if weather.wind.direction >= 0 else 0,
            weather.wind.speed,
        )

        # Get information letter
        info_letter = INFORMATION_LETTERS[self._current_letter_index]

        # Build the ATIS text and word list
        words, text = self._build_atis_content(
            airport_info["name"],
            info_letter,
            weather,
            active_runway,
            airport_info["ground_freq"],
            airport_icao=icao,  # Pass ICAO for chunk-based audio lookup
        )

        return ATISBroadcast(
            airport_icao=icao,
            airport_name=airport_info["name"],
            information_letter=info_letter,
            observation_time=weather.observation_time,
            weather=weather,
            active_runway=active_runway,
            text=text,
            words=words,
        )

    def _build_atis_content(
        self,
        airport_name: str,
        info_letter: str,
        weather: Weather,
        active_runway: str,
        ground_freq: float,
        airport_icao: str = "",
    ) -> tuple[list[str], str]:
        """Build ATIS content as word list and text.

        Args:
            airport_name: Full airport name.
            info_letter: Information letter.
            weather: Current weather.
            active_runway: Active runway.
            ground_freq: Ground frequency.
            airport_icao: Airport ICAO code for audio chunk lookup.

        Returns:
            Tuple of (words list, text string).
        """
        words: list[str] = []
        text_parts: list[str] = []

        # 1. Airport name and information
        # Use ICAO code as audio chunk identifier (e.g., "LFLY" plays "Lyon Bron")
        # This is the phrase chunk approach - one file contains the full airport name
        if airport_icao:
            words.append(airport_icao.upper())  # ICAO code as chunk identifier
        else:
            # Fallback to word-by-word for unknown airports
            name_words = airport_name.lower().split()
            words.extend(name_words)
        words.extend(["INFORMATION", info_letter])
        text_parts.append(f"{airport_name} information {info_letter}.")

        # 2. Time (Zulu) - phrase builder now includes TIME chunk
        obs_time = weather.observation_time
        time_phrase = self._phrase_builder.build_time_phrase(obs_time.hour, obs_time.minute)
        words.extend(time_phrase["words"])
        text_parts.append(f"{time_phrase['text'].capitalize()}.")

        # 3. Wind
        wind_phrase = self._phrase_builder.build_wind_phrase(
            weather.wind.direction, weather.wind.speed, weather.wind.gust
        )
        words.extend(wind_phrase["words"])
        text_parts.append(f"{wind_phrase['text'].capitalize()}.")

        # 4. Visibility
        vis_phrase = self._phrase_builder.build_visibility_phrase(weather.visibility)
        words.extend(vis_phrase["words"])
        text_parts.append(f"{vis_phrase['text'].capitalize()}.")

        # 5. Sky condition
        sky_words, sky_text = self._build_sky_phrase(weather)
        words.extend(sky_words)
        text_parts.append(f"{sky_text}.")

        # 6. Temperature and dewpoint
        temp_words, temp_text = self._build_temperature_phrase(
            weather.temperature, weather.dewpoint
        )
        words.extend(temp_words)
        text_parts.append(f"{temp_text}.")

        # 7. Altimeter/QNH
        alt_phrase = self._phrase_builder.build_altimeter_phrase(
            weather.altimeter, weather.pressure_unit
        )
        words.extend(alt_phrase["words"])
        text_parts.append(f"{alt_phrase['text'].capitalize()}.")

        # 8. Active runway (use phrase chunk)
        runway_words = PhoneticConverter.runway_to_phonetic(active_runway)
        words.append("LANDING_AND_DEPARTING_RUNWAY")
        words.extend(runway_words)
        text_parts.append(f"Landing and departing runway {' '.join(runway_words)}.")

        # 9. Contact ground for parking (use phrase chunks)
        freq_words = PhoneticConverter.frequency_to_phonetic(ground_freq)
        words.append("INBOUND_AIRCRAFT_CONTACT_GROUND_ON")
        words.extend(freq_words)
        words.append("FOR_PARKING_ASSIGNMENT")
        text_parts.append(
            f"Inbound aircraft contact ground on {' '.join(freq_words)} for parking assignment."
        )

        # 10. Advise on initial contact (use phrase chunks)
        words.append("ADVISE_ON_INITIAL_CONTACT")
        words.append("YOU_HAVE_INFORMATION")
        words.append(info_letter)
        text_parts.append(f"Advise on initial contact. You have information {info_letter}.")

        return words, " ".join(text_parts)

    def _build_sky_phrase(self, weather: Weather) -> tuple[list[str], str]:
        """Build sky condition phrase.

        Args:
            weather: Weather data.

        Returns:
            Tuple of (words, text).
        """
        if not weather.sky:
            return ["SKY_CLEAR"], "Sky clear"

        words = ["SKY_CONDITION"]
        text_parts = ["Sky condition"]

        # Map condition values to chunk IDs
        condition_chunks = {
            "few": "FEW",
            "scattered": "SCATTERED",
            "broken": "BROKEN",
            "overcast": "OVERCAST",
        }

        for layer in weather.sky:
            condition_word = layer.condition.value.lower()
            # Use chunk ID if available, otherwise fall back to word
            chunk_id = condition_chunks.get(condition_word, condition_word)
            words.append(chunk_id)

            # Convert altitude to words
            alt_hundreds = layer.altitude // 100
            alt_words = PhoneticConverter.number_to_individual_digits(alt_hundreds)
            # Pad to 3 digits
            while len(alt_words) < 3:
                alt_words.insert(0, "zero")
            words.extend(alt_words)

            text_parts.append(f"{condition_word} {alt_hundreds:03d}")

        return words, " ".join(text_parts)

    def _build_temperature_phrase(self, temp: int, dewpoint: int) -> tuple[list[str], str]:
        """Build temperature and dewpoint phrase.

        Args:
            temp: Temperature in Celsius.
            dewpoint: Dewpoint in Celsius.

        Returns:
            Tuple of (words, text).
        """
        words = ["TEMPERATURE"]

        if temp < 0:
            words.append("MINUS")
        temp_words = PhoneticConverter.number_to_individual_digits(abs(temp))
        words.extend(temp_words)

        words.append("DEWPOINT")
        if dewpoint < 0:
            words.append("MINUS")
        dew_words = PhoneticConverter.number_to_individual_digits(abs(dewpoint))
        words.extend(dew_words)

        temp_str = f"minus {abs(temp)}" if temp < 0 else str(temp)
        dew_str = f"minus {abs(dewpoint)}" if dewpoint < 0 else str(dewpoint)
        text = f"Temperature {temp_str}, dewpoint {dew_str}"

        return words, text

    def _weather_changed(self, old_weather: Weather | None, new_weather: Weather) -> bool:
        """Check if weather changed significantly.

        Args:
            old_weather: Previous weather data.
            new_weather: Current weather data.

        Returns:
            True if weather changed significantly.
        """
        if old_weather is None:
            return True

        # Check wind change
        wind_dir_change = abs(old_weather.wind.direction - new_weather.wind.direction)
        if wind_dir_change > 20:
            return True

        wind_speed_change = abs(old_weather.wind.speed - new_weather.wind.speed)
        if wind_speed_change > 5:
            return True

        # Check visibility change
        if abs(old_weather.visibility - new_weather.visibility) > 2:
            return True

        # Check altimeter change
        return abs(old_weather.altimeter - new_weather.altimeter) > 0.05

    def _advance_letter(self) -> None:
        """Advance to the next information letter."""
        self._current_letter_index = (self._current_letter_index + 1) % len(INFORMATION_LETTERS)

    def get_current_letter(self) -> str:
        """Get the current information letter."""
        return INFORMATION_LETTERS[self._current_letter_index]


class ATISAudioBuilder:
    """Build ATIS audio by concatenating word files.

    Assembles ATIS broadcasts from individual word audio files,
    with appropriate pauses between phrases.
    """

    def __init__(
        self,
        audio_base_path: str = "data/speech/en",
        voice_dir: str = "atc/atis",
    ) -> None:
        """Initialize audio builder.

        Args:
            audio_base_path: Base path for audio files.
            voice_dir: Voice directory within base path.
        """
        self.audio_base_path = Path(audio_base_path)
        self.voice_dir = voice_dir
        self._audio_cache: dict[str, Path] = {}

    def get_audio_files(self, words: list[str]) -> list[Path]:
        """Get list of audio file paths for words.

        Args:
            words: List of words to get audio for.

        Returns:
            List of paths to audio files.
        """
        files = []
        for word in words:
            audio_path = self._get_word_audio(word)
            if audio_path and audio_path.exists():
                files.append(audio_path)
            else:
                logger.warning("No audio file for word: %s", word)
        return files

    def _get_word_audio(self, word: str) -> Path | None:
        """Get audio file path for a single word.

        Args:
            word: Word to get audio for.

        Returns:
            Path to audio file, or None if not found.
        """
        word_lower = word.lower()

        # Check cache
        if word_lower in self._audio_cache:
            return self._audio_cache[word_lower]

        # Try different file naming conventions
        voice_path = self.audio_base_path / self.voice_dir

        # 1. Direct word match (uppercase for phonetic alphabet)
        candidates = [
            voice_path / f"{word.upper()}.ogg",
            voice_path / f"{word_lower}.ogg",
            voice_path / f"MSG_{word.upper()}.ogg",
        ]

        # 2. Number handling
        if word_lower in PhoneticConverter.PHONETIC_NUMBERS.values():
            # Find the digit for this phonetic word
            for digit, phonetic in PhoneticConverter.PHONETIC_NUMBERS.items():
                if phonetic == word_lower:
                    candidates.append(voice_path / f"MSG_NUMBER_{digit}.ogg")
                    break

        # 3. Try parent directories for shared words
        candidates.extend(
            [
                self.audio_base_path / "cockpit" / f"{word_lower}.ogg",
                self.audio_base_path / "pilot" / f"{word_lower}.ogg",
            ]
        )

        for candidate in candidates:
            if candidate.exists():
                self._audio_cache[word_lower] = candidate
                return candidate

        return None

    def has_all_audio(self, words: list[str]) -> tuple[bool, list[str]]:
        """Check if all words have audio files.

        Args:
            words: List of words to check.

        Returns:
            Tuple of (all_present, missing_words).
        """
        missing = []
        for word in words:
            audio_path = self._get_word_audio(word)
            if audio_path is None or not audio_path.exists():
                missing.append(word)

        return len(missing) == 0, missing

    def generate_missing_audio_list(self, words: list[str]) -> dict[str, str]:
        """Generate list of missing audio files needed.

        Args:
            words: List of words to check.

        Returns:
            Dict mapping filename to text to generate.
        """
        _, missing = self.has_all_audio(words)

        to_generate = {}
        for word in set(missing):
            filename = f"{word.upper()}.ogg"
            # Use the word itself as the text to speak
            text = word
            # Handle special cases
            if word.lower() == "niner":
                text = "niner"
            elif word.lower() in PhoneticConverter.PHONETIC_LETTERS.values():
                text = word.lower()

            to_generate[filename] = text

        return to_generate

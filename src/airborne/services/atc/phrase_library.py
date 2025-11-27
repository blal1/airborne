"""Phrase chunk library for natural ATC audio.

Provides a system for building ATC phrases from pre-recorded audio chunks
instead of word-by-word concatenation. This produces more natural-sounding
speech.

Chunks are defined in YAML config files per language and loaded at runtime.

Typical usage:
    from airborne.services.atc.phrase_library import PhraseLibrary, PhraseBuilder

    library = PhraseLibrary("en")
    builder = PhraseBuilder(library)

    # Build a taxi clearance
    audio_files = builder.build_taxi_clearance(
        callsign="N123AB",
        runway="31",
        taxiways=["A", "B"]
    )
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class Language(Enum):
    """Supported languages for ATC phraseology."""

    ENGLISH = "en"
    FRENCH = "fr"


@dataclass
class PhraseChunk:
    """A pre-recorded audio phrase chunk.

    Attributes:
        id: Unique chunk identifier.
        text: Display text for the chunk.
        audio_file: Filename of audio file (without path).
        category: Chunk category for organization.
    """

    id: str
    text: str
    audio_file: str
    category: str = "general"


@dataclass
class NumberPronunciation:
    """Number pronunciation rules for a language.

    Attributes:
        digits: Mapping of digit to pronunciation word.
        special_words: Special number words (thousand, hundred, etc.).
    """

    digits: dict[str, str] = field(default_factory=dict)
    special_words: dict[str, str] = field(default_factory=dict)


# English number pronunciation
ENGLISH_NUMBERS = NumberPronunciation(
    digits={
        "0": "zero",
        "1": "one",
        "2": "two",
        "3": "three",
        "4": "four",
        "5": "five",
        "6": "six",
        "7": "seven",
        "8": "eight",
        "9": "niner",  # Aviation pronunciation
    },
    special_words={
        "decimal": "decimal",
        "point": "point",
        "thousand": "thousand",
        "hundred": "hundred",
    },
)

# French number pronunciation
FRENCH_NUMBERS = NumberPronunciation(
    digits={
        "0": "zero",
        "1": "unite",  # Aviation French uses "unité" for 1
        "2": "deux",
        "3": "trois",
        "4": "quatre",
        "5": "cinq",
        "6": "six",
        "7": "sept",
        "8": "huit",
        "9": "neuf",  # No "niner" in French
    },
    special_words={
        "decimal": "virgule",
        "point": "point",
        "thousand": "mille",
        "hundred": "cent",
    },
)

# ICAO phonetic alphabet (same for all languages)
PHONETIC_ALPHABET = {
    "A": "alpha",
    "B": "bravo",
    "C": "charlie",
    "D": "delta",
    "E": "echo",
    "F": "foxtrot",
    "G": "golf",
    "H": "hotel",
    "I": "india",
    "J": "juliett",
    "K": "kilo",
    "L": "lima",
    "M": "mike",
    "N": "november",
    "O": "oscar",
    "P": "papa",
    "Q": "quebec",
    "R": "romeo",
    "S": "sierra",
    "T": "tango",
    "U": "uniform",
    "V": "victor",
    "W": "whiskey",
    "X": "xray",
    "Y": "yankee",
    "Z": "zulu",
}


class PhraseLibrary:
    """Library of phrase chunks for a specific language.

    Loads chunk definitions from YAML config and provides
    lookup functionality.

    Examples:
        >>> library = PhraseLibrary("en")
        >>> chunk = library.get_chunk("taxi_to_runway")
        >>> print(chunk.audio_file)  # "taxi_to_runway.ogg"
    """

    def __init__(
        self,
        language: str = "en",
        config_dir: str | Path = "config",
        audio_base_path: str | Path = "data/speech",
    ) -> None:
        """Initialize phrase library.

        Args:
            language: Language code ("en", "fr").
            config_dir: Directory containing phrase config files.
            audio_base_path: Base path for audio files.
        """
        self.language = language
        self.config_dir = Path(config_dir)
        self.audio_base_path = Path(audio_base_path) / language
        self._chunks: dict[str, PhraseChunk] = {}
        self._number_pronunciation = FRENCH_NUMBERS if language == "fr" else ENGLISH_NUMBERS

        self._load_default_chunks()
        self._load_config()

    def _load_default_chunks(self) -> None:
        """Load default chunk definitions."""
        # ATC instruction chunks
        default_chunks = [
            # Taxi instructions
            ("taxi_via", "taxi via", "atc/taxi_via.ogg", "taxi"),
            ("taxi_to_runway", "taxi to runway", "atc/taxi_to_runway.ogg", "taxi"),
            ("hold_short", "hold short", "atc/hold_short.ogg", "taxi"),
            ("hold_short_runway", "hold short runway", "atc/hold_short_runway.ogg", "taxi"),
            ("cross_runway", "cross runway", "atc/cross_runway.ogg", "taxi"),
            ("continue_taxi", "continue taxi", "atc/continue_taxi.ogg", "taxi"),
            ("continue_via", "continue via", "atc/continue_via.ogg", "taxi"),
            ("monitor_tower", "monitor tower", "atc/monitor_tower.ogg", "taxi"),
            ("contact_tower", "contact tower", "atc/contact_tower.ogg", "taxi"),
            ("contact_ground", "contact ground", "atc/contact_ground.ogg", "taxi"),
            # Clearances
            ("cleared_takeoff", "cleared for takeoff", "atc/cleared_takeoff.ogg", "clearance"),
            ("cleared_land", "cleared to land", "atc/cleared_land.ogg", "clearance"),
            (
                "cleared_touch_and_go",
                "cleared touch and go",
                "atc/cleared_touch_and_go.ogg",
                "clearance",
            ),
            ("cleared_option", "cleared for the option", "atc/cleared_option.ogg", "clearance"),
            ("line_up_wait", "line up and wait", "atc/line_up_wait.ogg", "clearance"),
            # Traffic
            ("traffic", "traffic", "atc/traffic.ogg", "traffic"),
            ("no_traffic", "no traffic reported", "atc/no_traffic.ogg", "traffic"),
            # Wind
            ("wind", "wind", "atc/wind.ogg", "weather"),
            ("wind_calm", "wind calm", "atc/wind_calm.ogg", "weather"),
            ("gusting", "gusting", "atc/gusting.ogg", "weather"),
            # Runway
            ("runway", "runway", "atc/runway.ogg", "runway"),
            ("left", "left", "atc/left.ogg", "runway"),
            ("right", "right", "atc/right.ogg", "runway"),
            ("center", "center", "atc/center.ogg", "runway"),
            # Frequency
            ("on", "on", "atc/on.ogg", "general"),
            ("at", "at", "atc/at.ogg", "general"),
            # Information
            (
                "you_have_information",
                "you have information",
                "atc/you_have_information.ogg",
                "info",
            ),
            ("advise_ready", "advise when ready", "atc/advise_ready.ogg", "info"),
            ("roger", "roger", "atc/roger.ogg", "general"),
            ("wilco", "wilco", "atc/wilco.ogg", "general"),
            ("affirm", "affirm", "atc/affirm.ogg", "general"),
            ("negative", "negative", "atc/negative.ogg", "general"),
            ("standby", "standby", "atc/standby.ogg", "general"),
            ("say_again", "say again", "atc/say_again.ogg", "general"),
            ("good_day", "good day", "atc/good_day.ogg", "general"),
        ]

        for chunk_id, text, audio_file, category in default_chunks:
            self._chunks[chunk_id] = PhraseChunk(
                id=chunk_id,
                text=text,
                audio_file=audio_file,
                category=category,
            )

    def _load_config(self) -> None:
        """Load phrase configuration from YAML file."""
        config_file = self.config_dir / f"phrases_{self.language}.yaml"
        if not config_file.exists():
            logger.debug("No phrase config found at %s, using defaults", config_file)
            return

        try:
            with open(config_file, encoding="utf-8") as f:
                config: dict[str, Any] = yaml.safe_load(f) or {}

            # Load chunks from config
            for chunk_id, chunk_data in config.get("chunks", {}).items():
                if isinstance(chunk_data, dict):
                    self._chunks[chunk_id] = PhraseChunk(
                        id=chunk_id,
                        text=chunk_data.get("text", chunk_id),
                        audio_file=chunk_data.get("audio_file", f"{chunk_id}.ogg"),
                        category=chunk_data.get("category", "general"),
                    )

            logger.info("Loaded %d phrase chunks from %s", len(self._chunks), config_file)

        except Exception as e:
            logger.warning("Error loading phrase config: %s", e)

    def get_chunk(self, chunk_id: str) -> PhraseChunk | None:
        """Get a phrase chunk by ID.

        Args:
            chunk_id: Chunk identifier.

        Returns:
            PhraseChunk if found, None otherwise.
        """
        return self._chunks.get(chunk_id)

    def get_audio_path(self, chunk_id: str) -> Path | None:
        """Get full audio file path for a chunk.

        Args:
            chunk_id: Chunk identifier.

        Returns:
            Full path to audio file, or None if chunk not found.
        """
        chunk = self._chunks.get(chunk_id)
        if not chunk:
            return None
        return self.audio_base_path / chunk.audio_file

    def get_number_pronunciation(self) -> NumberPronunciation:
        """Get number pronunciation rules for this language."""
        return self._number_pronunciation

    def get_phonetic_word(self, letter: str) -> str:
        """Get phonetic alphabet word for a letter.

        Args:
            letter: Single letter (A-Z).

        Returns:
            Phonetic word (e.g., "alpha" for "A").
        """
        return PHONETIC_ALPHABET.get(letter.upper(), letter.lower())


class PhraseBuilder:
    """Build ATC phrases from chunks and dynamic components.

    Combines phrase chunks with dynamic elements (callsigns, numbers,
    taxiways) to create complete audio sequences.

    Examples:
        >>> builder = PhraseBuilder(library)
        >>> files = builder.build_taxi_clearance("N123AB", "31", ["A", "B"])
        >>> # Returns list of audio file paths to play in sequence
    """

    def __init__(
        self,
        library: PhraseLibrary,
        voice_dir: str = "atc",
    ) -> None:
        """Initialize phrase builder.

        Args:
            library: PhraseLibrary to use for chunks.
            voice_dir: Voice subdirectory within audio base path.
        """
        self.library = library
        self.voice_dir = voice_dir
        self._numbers = library.get_number_pronunciation()

    def build_taxi_clearance(
        self,
        callsign: str,
        runway: str,
        taxiways: list[str],
        hold_short: bool = True,
    ) -> list[str]:
        """Build a taxi clearance phrase.

        Args:
            callsign: Aircraft callsign.
            runway: Destination runway.
            taxiways: List of taxiway names.
            hold_short: Whether to include hold short instruction.

        Returns:
            List of audio file paths (relative to audio base).

        Examples:
            >>> files = builder.build_taxi_clearance("N123AB", "31", ["A", "B"])
            >>> # ["atc/november.ogg", "atc/one.ogg", ..., "atc/taxi_via.ogg", ...]
        """
        audio_files = []

        # Callsign
        audio_files.extend(self._callsign_to_audio(callsign))

        # "taxi to runway"
        audio_files.append(f"{self.voice_dir}/taxi_to_runway.ogg")

        # Runway number
        audio_files.extend(self._runway_to_audio(runway))

        # "via"
        if taxiways:
            audio_files.append(f"{self.voice_dir}/taxi_via.ogg")
            # Taxiway names
            for taxiway in taxiways:
                audio_files.extend(self._taxiway_to_audio(taxiway))

        # Hold short if requested
        if hold_short:
            audio_files.append(f"{self.voice_dir}/hold_short_runway.ogg")
            audio_files.extend(self._runway_to_audio(runway))

        return audio_files

    def build_takeoff_clearance(
        self,
        callsign: str,
        runway: str,
        wind_direction: int | None = None,
        wind_speed: int | None = None,
    ) -> list[str]:
        """Build a takeoff clearance phrase.

        Args:
            callsign: Aircraft callsign.
            runway: Departure runway.
            wind_direction: Optional wind direction.
            wind_speed: Optional wind speed.

        Returns:
            List of audio file paths.
        """
        audio_files = []

        # Callsign
        audio_files.extend(self._callsign_to_audio(callsign))

        # Wind (if provided)
        if wind_direction is not None and wind_speed is not None:
            audio_files.extend(self._wind_to_audio(wind_direction, wind_speed))

        # "runway"
        audio_files.append(f"{self.voice_dir}/runway.ogg")

        # Runway number
        audio_files.extend(self._runway_to_audio(runway))

        # "cleared for takeoff"
        audio_files.append(f"{self.voice_dir}/cleared_takeoff.ogg")

        return audio_files

    def build_landing_clearance(
        self,
        callsign: str,
        runway: str,
        wind_direction: int | None = None,
        wind_speed: int | None = None,
    ) -> list[str]:
        """Build a landing clearance phrase.

        Args:
            callsign: Aircraft callsign.
            runway: Landing runway.
            wind_direction: Optional wind direction.
            wind_speed: Optional wind speed.

        Returns:
            List of audio file paths.
        """
        audio_files = []

        # Callsign
        audio_files.extend(self._callsign_to_audio(callsign))

        # Wind (if provided)
        if wind_direction is not None and wind_speed is not None:
            audio_files.extend(self._wind_to_audio(wind_direction, wind_speed))

        # "runway"
        audio_files.append(f"{self.voice_dir}/runway.ogg")

        # Runway number
        audio_files.extend(self._runway_to_audio(runway))

        # "cleared to land"
        audio_files.append(f"{self.voice_dir}/cleared_land.ogg")

        return audio_files

    def build_frequency_change(
        self,
        callsign: str,
        facility: str,
        frequency: float,
    ) -> list[str]:
        """Build a frequency change instruction.

        Args:
            callsign: Aircraft callsign.
            facility: ATC facility name ("tower", "ground", etc.).
            frequency: New frequency in MHz.

        Returns:
            List of audio file paths.
        """
        audio_files = []

        # Callsign
        audio_files.extend(self._callsign_to_audio(callsign))

        # "contact [facility]"
        if facility.lower() == "tower":
            audio_files.append(f"{self.voice_dir}/contact_tower.ogg")
        elif facility.lower() == "ground":
            audio_files.append(f"{self.voice_dir}/contact_ground.ogg")
        else:
            audio_files.append(f"{self.voice_dir}/contact.ogg")

        # "on"
        audio_files.append(f"{self.voice_dir}/on.ogg")

        # Frequency
        audio_files.extend(self._frequency_to_audio(frequency))

        return audio_files

    def build_hold_short(
        self,
        callsign: str,
        runway: str,
    ) -> list[str]:
        """Build a hold short instruction.

        Args:
            callsign: Aircraft callsign.
            runway: Runway to hold short of.

        Returns:
            List of audio file paths.
        """
        audio_files = []

        # Callsign
        audio_files.extend(self._callsign_to_audio(callsign))

        # "hold short runway"
        audio_files.append(f"{self.voice_dir}/hold_short_runway.ogg")

        # Runway number
        audio_files.extend(self._runway_to_audio(runway))

        return audio_files

    def _callsign_to_audio(self, callsign: str) -> list[str]:
        """Convert callsign to audio file list.

        Args:
            callsign: Aircraft callsign.

        Returns:
            List of audio file paths for phonetic callsign.
        """
        audio_files = []
        for char in callsign.upper():
            if char.isalpha():
                phonetic = self.library.get_phonetic_word(char)
                audio_files.append(f"{self.voice_dir}/{phonetic}.ogg")
            elif char.isdigit():
                word = self._numbers.digits.get(char, char)
                audio_files.append(f"{self.voice_dir}/{word}.ogg")
        return audio_files

    def _runway_to_audio(self, runway: str) -> list[str]:
        """Convert runway ID to audio file list.

        Args:
            runway: Runway identifier (e.g., "31", "09L").

        Returns:
            List of audio file paths.
        """
        audio_files = []
        for char in runway.upper():
            if char.isdigit():
                word = self._numbers.digits.get(char, char)
                audio_files.append(f"{self.voice_dir}/{word}.ogg")
            elif char == "L":
                audio_files.append(f"{self.voice_dir}/left.ogg")
            elif char == "R":
                audio_files.append(f"{self.voice_dir}/right.ogg")
            elif char == "C":
                audio_files.append(f"{self.voice_dir}/center.ogg")
        return audio_files

    def _taxiway_to_audio(self, taxiway: str) -> list[str]:
        """Convert taxiway name to audio file list.

        Args:
            taxiway: Taxiway name (e.g., "A", "B1").

        Returns:
            List of audio file paths.
        """
        audio_files = []
        for char in taxiway.upper():
            if char.isalpha():
                phonetic = self.library.get_phonetic_word(char)
                audio_files.append(f"{self.voice_dir}/{phonetic}.ogg")
            elif char.isdigit():
                word = self._numbers.digits.get(char, char)
                audio_files.append(f"{self.voice_dir}/{word}.ogg")
        return audio_files

    def _frequency_to_audio(self, frequency: float) -> list[str]:
        """Convert frequency to audio file list.

        Args:
            frequency: Frequency in MHz (e.g., 118.6).

        Returns:
            List of audio file paths.
        """
        audio_files = []
        freq_str = f"{frequency:.3f}"

        for char in freq_str:
            if char == ".":
                word = self._numbers.special_words.get("point", "point")
                audio_files.append(f"{self.voice_dir}/{word}.ogg")
            elif char.isdigit():
                word = self._numbers.digits.get(char, char)
                audio_files.append(f"{self.voice_dir}/{word}.ogg")

        return audio_files

    def _wind_to_audio(self, direction: int, speed: int) -> list[str]:
        """Convert wind info to audio file list.

        Args:
            direction: Wind direction in degrees.
            speed: Wind speed in knots.

        Returns:
            List of audio file paths.
        """
        audio_files = []

        # "wind"
        audio_files.append(f"{self.voice_dir}/wind.ogg")

        # Direction (3 digits)
        dir_str = f"{direction:03d}"
        for char in dir_str:
            word = self._numbers.digits.get(char, char)
            audio_files.append(f"{self.voice_dir}/{word}.ogg")

        # "at"
        audio_files.append(f"{self.voice_dir}/at.ogg")

        # Speed
        speed_str = str(speed)
        for char in speed_str:
            word = self._numbers.digits.get(char, char)
            audio_files.append(f"{self.voice_dir}/{word}.ogg")

        return audio_files
